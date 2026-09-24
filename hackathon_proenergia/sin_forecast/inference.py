from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .common import SUBMARKETS, TARGETS, WEATHER, strict_time
from .features import assert_temporal_contract, derive_weather, feature_columns, make_features

SCENARIO_FIELDS = {"temperature_delta", "radiation_multiplier", "cloud_override", "humidity_override", "holiday_override"}


def apply_scenario(frame, overrides):
    if set(overrides) - SCENARIO_FIELDS:
        raise ValueError(f"Variáveis de cenário desconhecidas: {set(overrides) - SCENARIO_FIELDS}")
    result = frame.copy()
    for name, value in overrides.items():
        if value is not None and (not isinstance(value, (int, float, bool)) or not np.isfinite(value)):
            raise ValueError(f"Valor inválido: {name}")
    delta = float(overrides.get("temperature_delta", 0))
    multiplier = float(overrides.get("radiation_multiplier", 1))
    if not -15 <= delta <= 15 or not 0 <= multiplier <= 2:
        raise ValueError("Cenário fora dos limites: temperatura ±15°C; multiplicador solar 0–2.")
    result["temperature"] += delta
    result["radiation"] *= multiplier
    for name, column in [("cloud_override", "cloud"), ("humidity_override", "humidity")]:
        value = overrides.get(name)
        if value is not None:
            if not 0 <= value <= 100:
                raise ValueError(f"{name} deve estar entre 0 e 100.")
            result[column] = float(value)
    if overrides.get("holiday_override") is not None:
        value = overrides["holiday_override"]
        if value not in (0, 1, False, True):
            raise ValueError("holiday_override deve ser 0 ou 1.")
        result["feriado_nacional"] = int(value)
        result["intensidade_feriado"] = float(value)
        result["frac_pop_feriado_estadual"] = 0
        for column in ["carnaval", "corpus_christi", "quarta_cinzas", "emenda"]:
            result[column] = 0
    result = derive_weather(result)
    result["scenario_json"] = json.dumps(overrides, ensure_ascii=False, sort_keys=True)
    return result


def predict_scenario(bundle, features, overrides):
    stale = [col for col in features if col.startswith(("pred_", "error_", "absolute_error_", "ape_", "scenario_delta"))]
    stale += [col for col in ["interval_contains_actual", "evaluation_generated_at"] if col in features]
    features = features.drop(columns=stale)
    changed = apply_scenario(features, overrides)
    base = bundle.predict(features)
    result = bundle.predict(changed)
    keys = ["horizon", "submercado", "origin_time", "target_time"]
    reference = base[keys + ["pred_final"]].rename(columns={"pred_final": "pred_original_scenario"})
    result = result.merge(reference, on=keys, how="left", validate="one_to_one")
    result["scenario_delta_mw"] = result.pred_final - result.pred_original_scenario
    result["scenario_delta_pct"] = 100 * result.scenario_delta_mw / result.pred_original_scenario
    result["outside_training_range"] = False
    for horizon, rows in result.groupby("horizon"):
        for column in WEATHER:
            low, high = bundle.feature_ranges.get(f"{horizon}:{column}", [-np.inf, np.inf])
            result.loc[rows.index, "outside_training_range"] |= ~rows[column].between(low, high)
    result["forecast_mode"] = "scenario_sensitivity_not_causal"
    return result


def external_weather(path, origin, submarket, horizon):
    frame = pd.read_csv(path)
    required = {"target_time", "issued_at", *WEATHER}
    if not required.issubset(frame):
        raise ValueError(f"Clima externo requer: {sorted(required)}")
    frame["target_time"] = strict_time(frame.target_time)
    frame["weather_issued_at_max"] = strict_time(frame.issued_at)
    if frame.weather_issued_at_max.gt(origin).any():
        raise ValueError("Clima externo contém previsão emitida depois da origem.")
    if not np.isfinite(frame[list(WEATHER)].to_numpy(dtype=float)).all():
        raise ValueError("Clima externo contém nulos ou valores não finitos.")
    valid = (frame.temperature.between(-30, 55) & frame.radiation.between(0, 1500)
             & frame.cloud.between(0, 100) & frame.humidity.between(0, 100))
    if not valid.all():
        raise ValueError("Clima externo fora das faixas físicas aceitas.")
    frame["submercado"], frame["horizon"] = submarket, horizon
    frame["weather_valid"] = True
    frame["weather_source"] = "external_snapshot_with_issued_at; radiation_mean_of_target_interval"
    return frame.drop(columns="issued_at")


def external_history(path):
    frame = pd.read_csv(path)
    required = {"submercado", "target_time", *TARGETS}
    if not required.issubset(frame):
        raise ValueError(f"Histórico externo requer: {sorted(required)}")
    frame["target_time"] = strict_time(frame.target_time)
    if frame.duplicated(["submercado", "target_time"]).any():
        raise ValueError("Histórico externo duplicado.")
    if not frame.target_time.eq(frame.target_time.dt.floor("h")).all():
        raise ValueError("Histórico deve identificar o início de cada hora.")
    frame["quality_ok"] = (np.isfinite(frame[list(TARGETS)]).all(axis=1) & frame.net.gt(0) & frame.gross.gt(0)
                           & frame.mmgd.ge(0) & (frame.gross - frame.mmgd - frame.net).abs().le(.02))
    frame.loc[~frame.quality_ok, list(TARGETS)] = np.nan
    return frame


def predict_request(request, artifact_dir: Path):
    bundle = joblib.load(artifact_dir / "models" / "forecast_bundle.joblib")
    origin = strict_time([request["origin_time"]]).iloc[0]
    if origin != origin.normalize():
        raise ValueError("Este modelo foi validado para emissão no fechamento do dia (00:00 Brasília).")
    horizon, submarket = int(request["horizon"]), request["submercado"]
    if horizon not in (1, 7) or submarket not in SUBMARKETS:
        raise ValueError("Horizonte ou submercado inválido.")
    if "weather_path" not in request:
        raise ValueError("Informe weather_path com as 24 previsões e issued_at; não há coleta ao vivo implícita.")
    hourly = (external_history(Path(request["history_path"])) if request.get("history_path")
              else pd.read_parquet(artifact_dir / "prepared" / "hourly.parquet"))
    hourly = hourly[hourly.submercado.eq(submarket) & (hourly.target_time + pd.Timedelta(hours=1)).le(origin)].copy()
    calendar = pd.read_parquet(artifact_dir / "prepared" / "calendar.parquet")
    if request.get("calendar_path"):
        calendar = pd.read_csv(request["calendar_path"])
        calendar["date"] = strict_time(calendar.date)
    supplied = external_weather(Path(request["weather_path"]), origin, submarket, horizon)
    old_weather = pd.read_parquet(artifact_dir / "prepared" / "weather.parquet")
    old_weather = old_weather[old_weather.submercado.eq(submarket) & old_weather.horizon.eq(horizon)
                              & old_weather.weather_issued_at_max.le(origin)]
    supplied_keys = supplied.set_index(["submercado", "target_time"]).index
    old_weather = old_weather[~old_weather.set_index(["submercado", "target_time"]).index.isin(supplied_keys)]
    weather = pd.concat([old_weather, supplied], ignore_index=True)
    start = origin + pd.Timedelta(days=horizon - 1)
    targets = pd.DataFrame({"submercado": submarket, "target_time": pd.date_range(start, periods=24, freq="h")})
    if not set(targets.target_time).issubset(set(supplied.target_time)):
        raise ValueError("Clima externo deve cobrir todas as 24 horas-alvo.")
    features = make_features(hourly, calendar, weather, horizon, targets)
    assert_temporal_contract(features, horizon)
    result = predict_scenario(bundle, features, request.get("overrides", {}))
    result["forecast_mode"] = "external_forecast_scenario" if request.get("overrides") else "external_forecast"
    return result
