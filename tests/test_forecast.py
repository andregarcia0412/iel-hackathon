from datetime import date

import pytest

from iel_hackathon.forecast import load_day_forecast


def test_forecast_is_last_day_with_net_and_gross_by_hour():
    forecast = load_day_forecast("SECO", 1)

    assert forecast.date == date(2026, 9, 22)
    assert len(forecast.net) == len(forecast.gross) == 24
    # 12h de 22/09 em SE/CO, D+1: carga líquida final e bruta prevista pelo modelo.
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
