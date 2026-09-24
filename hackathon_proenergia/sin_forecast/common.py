from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

TZ = "America/Sao_Paulo"
SUBMARKETS = ("N", "NE", "S", "SECO")
TARGETS = ("net", "gross", "mmgd")
WEATHER = ("temperature", "radiation", "cloud", "humidity")
LIMITATIONS = [
    "Backtest retrospectivo com carga ONS revisada; não há vintages históricos de publicação.",
    "Origem no fechamento de D: assume intervalos encerrados disponíveis sem latência.",
    "Clima histórico usa offsets Previous Runs, não uma única rodada comum rastreada.",
    "Meteorologia ponderada por população de capitais; MMGD é estimativa oficial.",
    "Intervalos empíricos calibrados antes do reajuste final; sem garantia de cobertura futura.",
    "Cenários são sensibilidades do modelo, não estimativas causais nem novos valores observados.",
]


def timestamp(value) -> pd.Timestamp:
    t = pd.Timestamp(value)
    return t.tz_localize(TZ) if t.tzinfo is None else t.tz_convert(TZ)


def strict_time(values):
    """Inputs externos precisam explicitar UTC ou offset; nunca adivinhar fuso."""
    series = pd.Series(values)
    if not series.astype(str).str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", regex=True).all():
        raise ValueError("Timestamps externos devem incluir timezone, por exemplo -03:00 ou Z.")
    return pd.to_datetime(series, utc=True).dt.tz_convert(TZ)


def json_default(value):
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=json_default, allow_nan=False), encoding="utf-8")


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def versions():
    return {name: importlib.metadata.version(name) for name in [
        "numpy", "pandas", "scikit-learn", "pyarrow", "joblib", "threadpoolctl", "streamlit", "plotly",
    ]}


def period_mask(frame, start, end):
    return frame.target_time.ge(timestamp(start)) & frame.target_time.lt(timestamp(end) + pd.Timedelta(days=1))
