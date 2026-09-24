"""Previsões do modelo para o último mês: carga líquida (data/last_month_predictions.csv) e bruta (data/last_month_components.csv)."""

import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_PREDICTIONS_PATH = _DATA_DIR / "last_month_predictions.csv"
# Gerado por scripts/extract_last_month_components.py.
_COMPONENTS_PATH = _DATA_DIR / "last_month_components.csv"

_KEYS = ["target_time", "submercado", "horizon"]
_HOURS = 24


@dataclass(frozen=True, kw_only=True)
class DayForecast:
    """Previsão de um dia, hora a hora (0h–23h), em MW. Hora sem previsão fica `None`."""

    date: date
    net: list[float | None]
    gross: list[float | None]


@st.cache_data
def _load() -> pd.DataFrame:
    predictions = pd.read_csv(_PREDICTIONS_PATH)
    # "final" é a combinação escolhida pelo modelo entre as abordagens direta e decomposta.
    net = predictions.loc[predictions["approach"] == "final", [*_KEYS, "prediction_mw"]]
    components = pd.read_csv(_COMPONENTS_PATH, usecols=[*_KEYS, "pred_gross"])
    merged = net.merge(components, on=_KEYS, how="left", validate="one_to_one")
    merged = merged.rename(columns={"prediction_mw": "net", "pred_gross": "gross"})
    # Horário de Brasília (-03:00): data e hora locais vêm direto do texto com o fuso.
    target_time = pd.to_datetime(merged["target_time"])
    return merged.assign(date=target_time.dt.date, hour=target_time.dt.hour)


def load_day_forecast(submercado: str, horizon: int) -> DayForecast:
    """Último dia com previsão do submercado ("SECO", "S", "NE" ou "N") no horizonte (1 ou 7 dias)."""
    data = _load()
    rows = data[(data["submercado"] == submercado) & (data["horizon"] == horizon)]
    if rows.empty:
        raise ValueError(f"Sem previsões para o submercado {submercado!r} no horizonte {horizon}.")
    day = rows["date"].max()
    by_hour = rows[rows["date"] == day].set_index("hour")
    return DayForecast(date=day, net=_hourly(by_hour["net"]), gross=_hourly(by_hour["gross"]))


def _hourly(values: pd.Series) -> list[float | None]:
    hourly = [values.get(hour) for hour in range(_HOURS)]
    return [None if value is None or math.isnan(value) else float(value) for value in hourly]
