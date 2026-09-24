"""Previsões do modelo para o último mês: carga líquida (data/last_month_predictions.csv), carga bruta, PLD, meteorologia e
calendário (data/last_month_components.csv) e potência de MMGD instalada (data/mmgd_capacity.csv)."""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_PREDICTIONS_PATH = _DATA_DIR / "last_month_predictions.csv"
# Gerados por scripts/extract_last_month_components.py.
_COMPONENTS_PATH = _DATA_DIR / "last_month_components.csv"
_CAPACITY_PATH = _DATA_DIR / "mmgd_capacity.csv"

_KEYS = ["target_time", "submercado", "horizon"]
_HOURS = 24
# Abordagens em last_month_predictions.csv. "final" é a combinação escolhida pelo modelo entre a direta e a decomposta;
# "baseline" é a carga da mesma hora na semana anterior.
_APPROACHES = ["baseline", "direct", "decomposed", "final"]
# Hora do card "Dados do período".
CONTEXT_HOUR = 13
# Faixas horárias da tabela de MAPE: (rótulo, hora inicial, hora final exclusiva).
MAPE_BANDS = (
    ("Madrugada 0h–6h", 0, 6),
    ("Manhã 6h–9h", 6, 9),
    ("Sol 9h–16h", 9, 16),
    ("Rampa 16h–19h", 16, 19),
    ("Noite 19h–24h", 19, 24),
)
_WEEKEND = (5, 6)  # sábado e domingo, com segunda = 0


@dataclass(frozen=True, kw_only=True)
class DayForecast:
    """Previsão de um dia, hora a hora (0h–23h), em MW. Hora sem previsão fica `None`."""

    date: date
    net: list[float | None]
    gross: list[float | None]


@dataclass(frozen=True, kw_only=True)
class PeriodSummary:
    """Desempenho no mês, para um submercado e horizonte.

    O erro evitado é a soma, hora a hora, de |erro do baseline| − |erro da previsão final|: em MWh (horas de 1h) e
    valorado ao PLD da hora, em R$. Não é energia economizada nem lucro, e sim o erro de previsão que deixou de existir.
    """

    avoided_error_mwh: float
    avoided_cost_brl: float
    mape_direct: float
    mape_decomposed: float


@dataclass(frozen=True, kw_only=True)
class DayContext:
    """Dados do dia previsto às `CONTEXT_HOUR` horas, como o modelo os usou."""

    date: date
    # Carga líquida prevista (final) menos a da mesma hora na semana anterior, em MW.
    net_change_mw: float
    radiation_wm2: float
    temperature_c: float
    # Potência de MMGD solar acumulada no último mês publicado até a data, em MW; `None` se não houver.
    mmgd_capacity_mw: float | None
    day_type: str


@st.cache_data
def _load() -> pd.DataFrame:
    predictions = pd.read_csv(_PREDICTIONS_PATH)
    # Uma linha por hora, submercado e horizonte: carga real ("actual") e a previsão de cada abordagem.
    wide = predictions.pivot(index=_KEYS, columns="approach", values="prediction_mw")[_APPROACHES]
    actual = predictions.drop_duplicates(_KEYS).set_index(_KEYS)["net"].rename("actual")
    merged = wide.join(actual).reset_index()
    components = pd.read_csv(_COMPONENTS_PATH)
    merged = merged.merge(components, on=_KEYS, how="left", validate="one_to_one")
    merged = merged.rename(columns={"pred_gross": "gross"})
    # Horário de Brasília (-03:00): data e hora locais vêm direto do texto com o fuso.
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
    """Último dia com previsão do submercado ("SECO", "S", "NE" ou "N") no horizonte (1 ou 7 dias)."""
    day = _last_day(_rows(submercado, horizon))
    by_hour = day.set_index("hour")
    return DayForecast(date=day["date"].iloc[0], net=_hourly(by_hour["final"]), gross=_hourly(by_hour["gross"]))


def load_period_summary(submercado: str, horizon: int) -> PeriodSummary:
    """Erro evitado e MAPE das abordagens em todas as horas do mês, para o submercado no horizonte."""
    rows = _rows(submercado, horizon)
    avoided = (rows["actual"] - rows["baseline"]).abs() - (rows["actual"] - rows["final"]).abs()
    return PeriodSummary(
        avoided_error_mwh=float(avoided.sum()),
        avoided_cost_brl=float((avoided * rows["pld_brl_mwh"]).sum()),
        mape_direct=_mape(rows, "direct"),
        mape_decomposed=_mape(rows, "decomposed"),
    )


def load_mape_by_band(horizon: int) -> dict[str, dict[str, float]]:
    """MAPE da previsão final no mês, em %, por submercado e faixa horária (rótulos de `MAPE_BANDS`)."""
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
    """Dados do mesmo dia de `load_day_forecast`, às `CONTEXT_HOUR` horas."""
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
    """Tipo do dia pelo calendário do modelo, do mais forte para o mais fraco."""
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
