import joblib
import numpy as np
import pandas as pd
import pytest

from sin_forecast.common import TARGETS, TZ, timestamp
from sin_forecast.data import CALENDAR_COLUMNS, hourly_load
from sin_forecast.features import add_splits, assert_temporal_contract, feature_columns, make_features
from sin_forecast.inference import apply_scenario, external_weather
from sin_forecast.models import ForecastBundle, fit_model, load_scales


@pytest.fixture(scope="module")
def source_tables():
    times = pd.date_range("2024-01-01", periods=100 * 24, freq="h", tz=TZ)
    g = 20 + 400 * np.maximum(0, np.sin((times.hour - 6) * np.pi / 12))
    b = 3000 + 250 * np.cos(times.hour * np.pi / 12)
    hourly = pd.DataFrame({"target_time": times, "submercado": "S", "net": b - g, "gross": b, "mmgd": g, "quality_ok": True})
    days = pd.date_range(times.min().normalize(), times.max().normalize(), freq="D")
    calendar = pd.DataFrame({"date": days, "submercado": "S", **{c: 0 for c in CALENDAR_COLUMNS}})
    weather = pd.concat([pd.DataFrame({"target_time": times, "submercado": "S", "horizon": h,
        "temperature": 25.0, "radiation": g, "cloud": 20.0, "humidity": 70.0,
        "weather_valid": True, "weather_issued_at_max": times + pd.Timedelta(hours=1) - pd.Timedelta(days=h),
        "weather_source": "test_forecast"}) for h in (1, 7)], ignore_index=True)
    return hourly, calendar, weather


def test_hourly_alignment_and_anomaly_not_hidden_by_mean():
    raw = pd.DataFrame({"cod_areacarga": ["N"] * 4,
        "din_referenciautc": ["2024-01-01T03:30Z", "2024-01-01T04:00Z", "2024-01-01T04:30Z", "2024-01-01T05:00Z"],
        "val_cargaglobalsmmgd": [100, 120, -10, 200], "val_cargaglobal": [110, 130, 0, 210], "val_cargammgd": [10] * 4})
    hourly, anomalies, report = hourly_load(raw)
    n = hourly[hourly.submercado.eq("N")].reset_index(drop=True)
    assert n.target_time.iloc[0] == timestamp("2024-01-01 00:00")
    assert n.net.iloc[0] == 110
    assert np.isnan(n.net.iloc[1]) and n.net_raw.iloc[1] == 95
    assert len(anomalies) == 1
    with pytest.raises(ValueError, match="duplicada"):
        hourly_load(pd.concat([raw, raw.iloc[:1]]))


@pytest.mark.parametrize("horizon", [1, 7])
def test_future_load_changes_cannot_change_features(source_tables, horizon):
    hourly, calendar, weather = source_tables
    origin = timestamp("2024-03-15")
    targets = pd.DataFrame({"submercado": "S", "target_time": pd.date_range(origin + pd.Timedelta(days=horizon - 1), periods=24, freq="h")})
    before = make_features(hourly, calendar, weather, horizon, targets)
    altered = hourly.copy()
    altered.loc[altered.target_time.ge(origin), ["net", "gross"]] += 10000
    after = make_features(altered, calendar, weather, horizon, targets)
    pd.testing.assert_frame_equal(before[feature_columns(horizon)], after[feature_columns(horizon)])
    assert before.feature_eligible.all()
    assert_temporal_contract(before, horizon)
    if horizon == 7:
        assert "net_lag24" not in feature_columns(horizon)


def test_proxy_and_post_origin_forecasts_are_excluded(source_tables):
    hourly, calendar, weather = source_tables
    weather = weather.copy()
    time = timestamp("2024-03-20 12:00")
    mask = weather.target_time.eq(time) & weather.horizon.eq(7)
    weather.loc[mask, "weather_valid"] = False
    f = make_features(hourly, calendar, weather, 7)
    row = f[f.target_time.eq(time)].iloc[0]
    assert not row.evaluation_eligible
    assert "forecast_missing" in row.exclusion_reason
    weather.loc[mask, "weather_valid"] = True
    weather.loc[mask, "weather_issued_at_max"] = time
    f = make_features(hourly, calendar, weather, 7)
    assert not f.loc[f.target_time.eq(time), "feature_eligible"].any()


def test_scenario_recomputes_dependent_features(source_tables):
    f = make_features(*source_tables, horizon=1)
    changed = apply_scenario(f, {"temperature_delta": 3, "radiation_multiplier": .5, "holiday_override": 1})
    np.testing.assert_allclose(changed.temperature_delta_week, f.temperature_delta_week + 3, equal_nan=True)
    np.testing.assert_allclose(changed.solar_generation_proxy, f.solar_generation_proxy * .5, equal_nan=True)
    assert changed.feriado_nacional.eq(1).all()
    assert changed.cooling_degrees.eq(6).all()
    with pytest.raises(ValueError):
        apply_scenario(f, {"net": 1000})


def test_saved_model_roundtrip_and_no_target_dependency(source_tables, tmp_path):
    f = make_features(*source_tables, horizon=1)
    eligible = f[f.evaluation_eligible]
    train = eligible[eligible.target_time.lt(timestamp("2024-03-01"))]
    test = eligible[eligible.target_time.ge(timestamp("2024-03-15"))].head(24)
    config = {"seed": 42, "n_jobs": 1, "interval_coverage": .9}
    scales = load_scales(train)
    models = {f"1:{t}": fit_model(train, t, 1, "ridge", config, scales) for t in TARGETS}
    bundle = ForecastBundle(models, {"1": scales}, {f"1:{t}": "ridge" for t in TARGETS}, config, "test", "2024-02-29")
    p1 = bundle.predict(test)
    changed = test.copy()
    changed[list(TARGETS)] = 1e9
    p2 = bundle.predict(changed)
    np.testing.assert_allclose(p1.pred_final, p2.pred_final)
    path = tmp_path / "model.joblib"
    joblib.dump(bundle, path)
    np.testing.assert_allclose(p1.pred_final, joblib.load(path).predict(test).pred_final)
    with pytest.raises(ValueError, match="Origem anterior"):
        bundle.predict(train.head(1))


def test_external_weather_requires_real_availability_and_timezone(tmp_path):
    path = tmp_path / "weather.csv"
    frame = pd.DataFrame({"target_time": ["2026-09-25T00:00:00-03:00"], "issued_at": ["2026-09-25T01:00:00-03:00"],
                          "temperature": [25], "radiation": [0], "cloud": [20], "humidity": [50]})
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="depois da origem"):
        external_weather(path, timestamp("2026-09-25"), "S", 1)
    frame["issued_at"] = "2026-09-24 00:00:00"
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="timezone"):
        external_weather(path, timestamp("2026-09-25"), "S", 1)


def test_d7_split_rejects_origins_before_training_close(source_tables):
    f = make_features(*source_tables, horizon=7)
    config = {"train_start": "2024-02-01", "train_end": "2024-02-29", "tune_start": "2024-03-01", "tune_end": "2024-03-10",
              "selection_start": "2024-03-20", "selection_end": "2024-03-25", "calibration_start": "2024-04-02",
              "calibration_end": "2024-04-05", "test_start": "2024-04-08", "test_end": "2024-04-09", "refit_end": "2024-03-31"}
    with pytest.raises(ValueError, match="Origem do split tune"):
        add_splits(f, config)
