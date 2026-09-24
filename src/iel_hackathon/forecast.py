import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_PREDICTIONS_PATH = _DATA_DIR / "last_month_predictions.csv"
_COMPONENTS_PATH = _DATA_DIR / "last_month_components.csv"
_CAPACITY_PATH = _DATA_DIR / "mmgd_capacity.csv"

_KEYS = ["target_time", "submercado", "horizon"]
_HOURS = 24
_APPROACHES = ["baseline", "direct", "decomposed", "final"]
CONTEXT_HOUR = 13
MAPE_BANDS = (
    ("Madrugada 0h–6h", 0, 6),
    ("Manhã 6h–9h", 6, 9),
    ("Sol 9h–16h", 9, 16),
    ("Rampa 16h–19h", 16, 19),
    ("Noite 19h–24h", 19, 24),
)
_WEEKEND = (5, 6)


@dataclass(frozen=True, kw_only=True)
class DayForecast:
    date: date
    net: list[float | None]
    gross: list[float | None]


@dataclass(frozen=True, kw_only=True)
class PeriodSummary:
    avoided_error_mwh: float
    avoided_cost_brl: float
    mape_direct: float
    mape_decomposed: float


@dataclass(frozen=True, kw_only=True)
class DayContext:
    date: date
    net_change_mw: float
    radiation_wm2: float
    temperature_c: float
    mmgd_capacity_mw: float | None
    day_type: str


@st.cache_data
def _load() -> pd.DataFrame:
    predictions = pd.read_csv(_PREDICTIONS_PATH)
    wide = predictions.pivot(index=_KEYS, columns="approach", values="prediction_mw")[_APPROACHES]
    actual = predictions.drop_duplicates(_KEYS).set_index(_KEYS)["net"].rename("actual")
    merged = wide.join(actual).reset_index()
    components = pd.read_csv(_COMPONENTS_PATH)
    merged = merged.merge(components, on=_KEYS, how="left", validate="one_to_one")
    merged = merged.rename(columns={"pred_gross": "gross"})
    target_time = pd.to_datetime(merged["target_time"])
    return merged.assign(date=target_time.dt.date, hour=target_time.dt.hour)


@st.cache_data
def _load_capacity() -> pd.DataFrame:
    return pd.read_csv(_CAPACITY_PATH)


def _rows(submercado: str, horizon: int) -> pd.DataFrame:
    data = _load()
    rows = data[(data["submercado"] == submercado) & (data["horizon"] == horizon)]
    if rows.empty:
        raise ValueError(f"Sem previsões para o submercado {submercado!r} no horizonte {horizon}.")
    return rows


def _last_day(rows: pd.DataFrame) -> pd.DataFrame:
    return rows[rows["date"] == rows["date"].max()]


def load_day_forecast(submercado: str, horizon: int) -> DayForecast:
    day = _last_day(_rows(submercado, horizon))
    by_hour = day.set_index("hour")
    return DayForecast(date=day["date"].iloc[0], net=_hourly(by_hour["final"]), gross=_hourly(by_hour["gross"]))


def load_period_summary(submercado: str, horizon: int) -> PeriodSummary:
    rows = _rows(submercado, horizon)
    avoided = (rows["actual"] - rows["baseline"]).abs() - (rows["actual"] - rows["final"]).abs()
    return PeriodSummary(
        avoided_error_mwh=float(avoided.sum()),
        avoided_cost_brl=float((avoided * rows["pld_brl_mwh"]).sum()),
        mape_direct=_mape(rows, "direct"),
        mape_decomposed=_mape(rows, "decomposed"),
    )


def load_mape_by_band(horizon: int) -> dict[str, dict[str, float]]:
    data = _load()
    rows = data[data["horizon"] == horizon]
    return {
        submercado: {
            label: _mape(by_submercado[by_submercado["hour"].between(start, end - 1)], "final")
            for label, start, end in MAPE_BANDS
        }
        for submercado, by_submercado in rows.groupby("submercado")
    }


def load_day_context(submercado: str, horizon: int) -> DayContext:
    day = _last_day(_rows(submercado, horizon))
    row = day[day["hour"] == CONTEXT_HOUR]
    if row.empty:
        raise ValueError(f"Sem previsão às {CONTEXT_HOUR}h para o submercado {submercado!r} no horizonte {horizon}.")
    row = row.iloc[0]
    return DayContext(
        date=row["date"],
        net_change_mw=float(row["final"] - row["baseline"]),
        radiation_wm2=float(row["radiation"]),
        temperature_c=float(row["temperature"]),
        mmgd_capacity_mw=_capacity(submercado, row["date"]),
        day_type=_day_type(row),
    )


def _mape(rows: pd.DataFrame, approach: str) -> float:
    return float(((rows["actual"] - rows[approach]).abs() / rows["actual"]).mean() * 100)


def _capacity(submercado: str, day: date) -> float | None:
    capacity = _load_capacity()
    published = capacity[(capacity["submercado"] == submercado) & (capacity["mes"] <= f"{day:%Y-%m}")]
    if published.empty:
        return None
    return float(published.sort_values("mes")["mw_acumulado"].iloc[-1])


def _day_type(row: Mapping) -> str:
    if row["feriado_nacional"] or row["carnaval"] or row["corpus_christi"]:
        return "feriado"
    if row["emenda"]:
        return "emenda"
    if row["frac_pop_feriado_estadual"] > 0:
        return "feriado estadual"
    if row["vespera_feriado"]:
        return "véspera de feriado"
    if row["pos_feriado"]:
        return "pós-feriado"
    if row["weekday"] in _WEEKEND:
        return "fim de semana"
    return "dia útil"


def _hourly(values: pd.Series) -> list[float | None]:
    hourly = [values.get(hour) for hour in range(_HOURS)]
    return [None if value is None or math.isnan(value) else float(value) for value in hourly]
