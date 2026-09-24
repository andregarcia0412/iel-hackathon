import math
from datetime import date

import pandas as pd
import pytest

from iel_hackathon import forecast
from iel_hackathon.forecast import (
    MAPE_BANDS,
    load_day_context,
    load_day_forecast,
    load_mape_by_band,
    load_period_summary,
)

PREDICTIONS = forecast._PREDICTIONS_PATH
COMPONENTS = forecast._COMPONENTS_PATH


def test_forecast_is_last_day_with_net_and_gross_by_hour():
    forecast = load_day_forecast("SECO", 1)

    assert forecast.date == date(2026, 9, 22)
    assert len(forecast.net) == len(forecast.gross) == 24
    assert forecast.net[12] == pytest.approx(36_792, abs=1)
    assert forecast.gross[12] == pytest.approx(52_653, abs=1)


@pytest.mark.parametrize("submercado", ["SECO", "S", "NE", "N"])
@pytest.mark.parametrize("horizon", [1, 7])
def test_forecast_has_every_hour_for_each_filter(submercado, horizon):
    forecast = load_day_forecast(submercado, horizon)

    assert None not in forecast.net
    assert None not in forecast.gross


def test_forecast_rejects_unknown_submercado():
    with pytest.raises(ValueError):
        load_day_forecast("XX", 1)


def _month(submercado: str, horizon: int) -> pd.DataFrame:
    predictions = pd.read_csv(PREDICTIONS)
    rows = predictions[(predictions["submercado"] == submercado) & (predictions["horizon"] == horizon)]
    return rows.pivot(index="target_time", columns="approach", values="prediction_mw").join(
        rows.drop_duplicates("target_time").set_index("target_time")["net"]
    )


def test_period_summary_matches_the_csv():
    rows = _month("SECO", 1)
    pld = pd.read_csv(COMPONENTS).query("submercado == 'SECO' and horizon == 1").set_index("target_time")["pld_brl_mwh"]
    avoided = (rows["net"] - rows["baseline"]).abs() - (rows["net"] - rows["final"]).abs()

    summary = load_period_summary("SECO", 1)

    assert summary.avoided_error_mwh == pytest.approx(avoided.sum())
    assert summary.avoided_cost_brl == pytest.approx((avoided * pld).sum())
    assert summary.mape_direct == pytest.approx(((rows["net"] - rows["direct"]).abs() / rows["net"]).mean() * 100)
    assert summary.mape_decomposed == pytest.approx(
        ((rows["net"] - rows["decomposed"]).abs() / rows["net"]).mean() * 100
    )
    assert summary.avoided_error_mwh > 0


@pytest.mark.parametrize("horizon", [1, 7])
def test_mape_by_band_has_every_submercado_and_band(horizon):
    mape = load_mape_by_band(horizon)

    assert set(mape) == {"SECO", "S", "NE", "N"}
    for bands in mape.values():
        assert list(bands) == [label for label, _, _ in MAPE_BANDS]
        assert all(math.isfinite(value) and value > 0 for value in bands.values())


def test_mape_band_uses_hours_from_start_to_end_exclusive():
    rows = _month("S", 1)
    hours = pd.to_datetime(rows.index).hour
    sun = rows[(hours >= 9) & (hours < 16)]

    assert load_mape_by_band(1)["S"]["Sol 9h–16h"] == pytest.approx(
        ((sun["net"] - sun["final"]).abs() / sun["net"]).mean() * 100
    )


def test_day_context_is_the_forecast_day_at_13h():
    context = load_day_context("SECO", 1)
    row = _month("SECO", 1).loc["2026-09-22 13:00:00-03:00"]

    assert context.date == load_day_forecast("SECO", 1).date == date(2026, 9, 22)
    assert context.net_change_mw == pytest.approx(row["final"] - row["baseline"])
    assert context.temperature_c == pytest.approx(27.35, abs=0.01)
    assert context.radiation_wm2 == pytest.approx(623.76, abs=0.01)
    assert context.mmgd_capacity_mw == pytest.approx(26_339.945)
    assert context.day_type == "dia útil"


@pytest.mark.parametrize(
    ("changes", "day_type"),
    [
        ({"feriado_nacional": 1, "emenda": 1}, "feriado"),
        ({"emenda": 1}, "emenda"),
        ({"frac_pop_feriado_estadual": 0.3}, "feriado estadual"),
        ({"vespera_feriado": 1}, "véspera de feriado"),
        ({"pos_feriado": 1}, "pós-feriado"),
        ({"weekday": 6}, "fim de semana"),
        ({}, "dia útil"),
    ],
)
def test_day_type_follows_the_calendar(changes, day_type):
    row = {
        "feriado_nacional": 0,
        "carnaval": 0,
        "corpus_christi": 0,
        "emenda": 0,
        "frac_pop_feriado_estadual": 0.0,
        "vespera_feriado": 0,
        "pos_feriado": 0,
        "weekday": 1,
        **changes,
    }

    assert forecast._day_type(row) == day_type
