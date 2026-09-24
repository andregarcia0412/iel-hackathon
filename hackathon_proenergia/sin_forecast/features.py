from __future__ import annotations

import numpy as np
import pandas as pd

from .common import SUBMARKETS, TARGETS, WEATHER, period_mask, timestamp
from .data import CALENDAR_COLUMNS

BASE_FEATURES = [
    "hour", "weekday", "month", "hour_sin", "hour_cos", "year_sin", "year_cos", "is_solar",
    *[f"sub_{s}" for s in SUBMARKETS], *CALENDAR_COLUMNS,
    "holiday_last_week", "holiday_change", *WEATHER,
    "temperature_last_week_forecast", "radiation_last_week_forecast",
    "temperature_delta_week", "radiation_delta_week", "cooling_degrees", "heating_degrees",
    "solar_generation_proxy", "night_mmgd_level", "mmgd_scale",
]


def feature_columns(horizon):
    lags = [168, 336, 672] + ([24, 48] if horizon == 1 else [])
    return BASE_FEATURES + [f"{target}_lag{lag}" for target in TARGETS for lag in lags] + [
        f"{target}_{stat}" for target in TARGETS for stat in ["mean24_origin", "mean168_origin", "trend_origin"]
    ]


def derive_weather(frame):
    f = frame.copy()
    f["temperature_delta_week"] = f.temperature - f.temperature_last_week_forecast
    f["radiation_delta_week"] = f.radiation - f.radiation_last_week_forecast
    f["cooling_degrees"] = (f.temperature - 22).clip(lower=0)
    f["heating_degrees"] = (18 - f.temperature).clip(lower=0)
    f["solar_generation_proxy"] = f.mmgd_scale * f.radiation / 1000
    f["holiday_change"] = f.intensidade_feriado - f.holiday_last_week
    return f


def make_features(hourly, calendar, weather, horizon, targets=None):
    if horizon not in (1, 7):
        raise ValueError("Horizontes implementados: 1 e 7 dias.")
    if targets is None:
        f = hourly.copy()
    else:
        if targets.duplicated(["submercado", "target_time"]).any():
            raise ValueError("Alvos duplicados.")
        f = targets.merge(hourly, on=["submercado", "target_time"], how="left", validate="one_to_one")
    f = f.sort_values(["submercado", "target_time"]).reset_index(drop=True)
    f["horizon"] = horizon
    f["origin_time"] = f.target_time.dt.normalize() - pd.Timedelta(days=horizon - 1)
    f["lead_hours_to_interval_end"] = (f.target_time + pd.Timedelta(hours=1) - f.origin_time).dt.total_seconds() / 3600
    f["date"] = f.target_time.dt.normalize()
    f = f.merge(calendar, on=["submercado", "date"], how="left", validate="many_to_one")
    f["calendar_valid"] = f[CALENDAR_COLUMNS].notna().all(axis=1)
    prior_calendar = calendar[["submercado", "date", "intensidade_feriado"]].copy()
    prior_calendar["date"] += pd.Timedelta(days=7)
    f = f.merge(prior_calendar.rename(columns={"intensidade_feriado": "holiday_last_week"}),
                on=["submercado", "date"], how="left", validate="many_to_one")
    w = weather.loc[weather.horizon.eq(horizon)].copy()
    if w.duplicated(["submercado", "target_time"]).any():
        raise ValueError("Previsões meteorológicas duplicadas.")
    f = f.merge(w.drop(columns="horizon"), on=["submercado", "target_time"], how="left", validate="one_to_one")
    old_weather = w[["submercado", "target_time", "temperature", "radiation"]].copy()
    old_weather["target_time"] += pd.Timedelta(days=7)
    old_weather = old_weather.rename(columns={"temperature": "temperature_last_week_forecast", "radiation": "radiation_last_week_forecast"})
    f = f.merge(old_weather, on=["submercado", "target_time"], how="left", validate="one_to_one")
    f["weather_valid"] = f.weather_valid.eq(True)
    f["weather_asof_ok"] = f.weather_issued_at_max.le(f.origin_time)
    f["hour"] = f.target_time.dt.hour
    f["weekday"] = f.target_time.dt.dayofweek
    f["month"] = f.target_time.dt.month
    f["is_solar"] = f.hour.between(8, 16).astype(int)
    for name, values, period in [("hour", f.hour, 24), ("year", f.target_time.dt.dayofyear, 365.25)]:
        f[f"{name}_sin"] = np.sin(2 * np.pi * values / period)
        f[f"{name}_cos"] = np.cos(2 * np.pi * values / period)
    for sub in SUBMARKETS:
        f[f"sub_{sub}"] = f.submercado.eq(sub).astype(int)

    pieces = []
    lags = [168, 336, 672] + ([24, 48] if horizon == 1 else [])
    for sub, rows in f.groupby("submercado", sort=False):
        rows = rows.copy()
        hist = hourly.loc[hourly.submercado.eq(sub)].sort_values("target_time").set_index("target_time")
        if hist.empty:
            raise ValueError(f"Histórico ausente: {sub}")
        hist = hist.reindex(pd.date_range(hist.index.min(), hist.index.max(), freq="h"))
        ends = pd.DatetimeIndex(rows.origin_time - pd.Timedelta(hours=1))
        for target in TARGETS:
            series = hist[target]
            for lag in lags:
                rows[f"{target}_lag{lag}"] = series.reindex(pd.DatetimeIndex(rows.target_time - pd.Timedelta(hours=lag))).to_numpy()
            mean24 = series.rolling(24, min_periods=18).mean()
            mean168 = series.rolling(168, min_periods=144).mean()
            trend = mean168 - mean168.shift(168)
            for name, values in [("mean24_origin", mean24), ("mean168_origin", mean168), ("trend_origin", trend)]:
                rows[f"{target}_{name}"] = values.reindex(ends).to_numpy()
        solar = hist.mmgd.where(hist.index.hour.isin(range(8, 17)))
        scale = solar.rolling(28 * 24, min_periods=21 * 9).quantile(.95).clip(lower=1)
        night = hist.mmgd.where(hist.index.hour <= 4).rolling(14 * 24, min_periods=50).median()
        rows["mmgd_scale"] = scale.reindex(ends).to_numpy()
        rows["night_mmgd_level"] = night.reindex(ends).to_numpy()
        valid_ends = pd.Series(hist.index + pd.Timedelta(hours=1), index=hist.index).where(hist.net.notna()).ffill()
        rows["history_latest_end"] = valid_ends.reindex(ends).to_numpy()
        pieces.append(rows)
    f = pd.concat(pieces, ignore_index=True)
    f["history_latest_end"] = pd.to_datetime(f.history_latest_end, utc=True).dt.tz_convert(f.origin_time.dt.tz)
    f["history_age_hours"] = (f.origin_time - f.history_latest_end).dt.total_seconds() / 3600
    f["history_valid"] = f.history_age_hours.between(0, 24) & f.mmgd_scale.notna() & f.net_mean168_origin.notna()
    f["baseline_valid"] = f[[f"{t}_lag168" for t in TARGETS]].notna().all(axis=1) & f.net_lag168.gt(0)
    f["feature_eligible"] = f.calendar_valid & f.weather_valid & f.weather_asof_ok & f.history_valid & f.baseline_valid
    f["target_valid"] = f[list(TARGETS)].notna().all(axis=1) & f.net.gt(0)
    f["evaluation_eligible"] = f.feature_eligible & f.target_valid
    f["exclusion_reason"] = ""
    for col, reason in [("calendar_valid", "calendar_missing"), ("weather_valid", "forecast_missing_or_invalid"),
                        ("weather_asof_ok", "forecast_unavailable_at_origin"), ("history_valid", "history_missing_or_stale"),
                        ("baseline_valid", "baseline_missing"), ("target_valid", "target_invalid_or_unknown")]:
        f.loc[~f[col], "exclusion_reason"] += reason + ";"
    return derive_weather(f).sort_values(["origin_time", "submercado", "target_time"]).reset_index(drop=True)


def add_splits(frame, config):
    f = frame.copy()
    f["split"] = "unused"
    for split in ["train", "tune", "selection", "calibration", "test"]:
        mask = period_mask(f, config[f"{split}_start"], config[f"{split}_end"])
        if f.loc[mask, "split"].ne("unused").any():
            raise ValueError("Splits sobrepostos.")
        f.loc[mask, "split"] = split
    cutoffs = {"tune": config["train_end"], "selection": config["tune_end"],
               "calibration": config["selection_end"], "test": config["refit_end"]}
    for split, end in cutoffs.items():
        cutoff = timestamp(end) + pd.Timedelta(days=1)
        if (f.loc[f.split.eq(split), "origin_time"] < cutoff).any():
            raise ValueError(f"Origem do split {split} anterior ao fechamento de {end}.")
    f["refit_eligible"] = period_mask(f, config["train_start"], config["refit_end"]) & f.evaluation_eligible
    return f


def assert_temporal_contract(frame, horizon):
    valid = frame.loc[frame.feature_eligible]
    if not valid.weather_issued_at_max.le(valid.origin_time).all():
        raise AssertionError("Previsão meteorológica posterior à origem.")
    if not valid.history_latest_end.le(valid.origin_time).all():
        raise AssertionError("Histórico posterior à origem.")
    for lag in [168, 336, 672] + ([24, 48] if horizon == 1 else []):
        if not (valid.target_time - pd.Timedelta(hours=lag) + pd.Timedelta(hours=1)).le(valid.origin_time).all():
            raise AssertionError(f"Lag {lag} não está disponível na origem.")
    forbidden = set(TARGETS) | {"net_raw", "gross_raw", "mmgd_raw", "pld_brl_mwh", "source_updated_at"}
    if forbidden.intersection(feature_columns(horizon)):
        raise AssertionError("Alvo ou variável ex post incluído nas features.")
