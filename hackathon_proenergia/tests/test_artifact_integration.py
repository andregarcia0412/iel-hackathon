from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from sin_forecast.inference import predict_request, predict_scenario

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
READY = (ARTIFACTS / "manifest.json").exists()
pytestmark = pytest.mark.skipif(not READY, reason="Execute a pipeline completa para verificar os artefatos reais.")


@pytest.fixture(scope="module")
def outputs():
    bundle = joblib.load(ARTIFACTS / "models" / "forecast_bundle.joblib")
    predictions = pd.read_parquet(ARTIFACTS / "reports" / "test_predictions.parquet")
    return bundle, predictions


def test_persisted_predictions_match_reloaded_model(outputs):
    bundle, predictions = outputs
    for h in (1, 7):
        rows = predictions[predictions.horizon.eq(h)].tail(96)
        current = bundle.predict(rows)
        np.testing.assert_allclose(current.pred_final, rows.sort_values(["origin_time", "submercado", "target_time"]).pred_final, atol=1e-9)
        assert len(rows) == 96


def test_scenario_changes_predictions_and_preserves_original(outputs):
    bundle, predictions = outputs
    rows = predictions[predictions.horizon.eq(1) & predictions.submercado.eq("S")].tail(24)
    same = predict_scenario(bundle, rows, {})
    np.testing.assert_allclose(same.scenario_delta_mw, 0, atol=1e-9)
    changed = predict_scenario(bundle, rows, {"temperature_delta": 5, "radiation_multiplier": .5})
    assert (changed.scenario_delta_mw.abs() > 1).any()
    assert "ape_final_pct" not in changed and "interval_contains_actual" not in changed


@pytest.mark.parametrize("horizon", [1, 7])
def test_external_inference_matches_replay_and_hides_future_labels(outputs, tmp_path, horizon):
    bundle, predictions = outputs
    rows = predictions[predictions.horizon.eq(horizon) & predictions.submercado.eq("NE")].tail(24)
    weather = rows[["target_time", "weather_issued_at_max", "temperature", "radiation", "cloud", "humidity"]].rename(columns={"weather_issued_at_max": "issued_at"})
    path = tmp_path / "weather.csv"
    weather.to_csv(path, index=False)
    request = {"origin_time": str(rows.origin_time.iloc[0]), "horizon": horizon, "submercado": "NE", "weather_path": str(path)}
    result = predict_request(request, ARTIFACTS)
    np.testing.assert_allclose(result.pred_final, rows.pred_final, atol=1e-7)
    assert result.net.isna().all()
    assert len(result) == 24
