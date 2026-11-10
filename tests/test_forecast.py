"""Forecast tests: parsing, inheritance, analytics, and that forecasts never get logged."""

import pytest

from weather_app import analytics
from weather_app.client import OpenWeatherClient
from weather_app.exceptions import APIServiceError, LocationNotFoundError
from weather_app.models import Forecast, ForecastPoint, WeatherSnapshot
from weather_app.storage import WeatherLog
from test_client import FakeResponse, FakeSession

# 2026-11-01 00:00 UTC = 01:00 in Madrid; steps every 3 hours
T0 = 1793491200


def item(hours, temp, humidity=50, wind=1.0, pop=0.0, rain=None, desc="clear sky"):
    out = {
        "dt": T0 + hours * 3600,
        "main": {"temp": temp, "feels_like": temp - 1, "temp_min": temp, "temp_max": temp,
                 "pressure": 1015, "humidity": humidity},
        "weather": [{"description": desc}],
        "wind": {"speed": wind},
        "clouds": {"all": 10},
        "pop": pop,
    }
    if rain is not None:
        out["rain"] = {"3h": rain}
    return out


@pytest.fixture
def forecast_json():
    return {
        "cod": "200",
        "city": {"name": "Madrid", "country": "ES", "coord": {"lat": 40.4, "lon": -3.7}},
        "list": [
            item(0, 10.0),                                   # 01:00 Madrid, night
            item(9, 21.0, pop=0.1),                          # 10:00, perfect & dry
            item(12, 23.0, pop=0.8, rain=2.5, desc="rain"),  # 13:00, warmer but rainy
            item(24, 8.0, pop=0.4, rain=1.0, desc="rain"),   # next day 01:00
            item(33, 15.0),                                  # next day 10:00
        ],
    }


def test_forecast_parses(forecast_json):
    fc = Forecast.from_api(forecast_json)
    assert len(fc) == 5
    assert fc.label == "Madrid, ES"
    assert repr(fc) == "Forecast('Madrid, ES', 5 points)"
    assert [p.temperature for p in fc][:2] == [10.0, 21.0]   # __iter__


def test_forecast_point_inherits_snapshot_behaviour(forecast_json):
    point = Forecast.from_api(forecast_json).points[2]
    assert isinstance(point, WeatherSnapshot)
    assert point.rain_chance_pct == 80
    assert point.rain_mm == 2.5
    assert point.wind_kmh == 3.6            # inherited property
    assert point.comfort_index == 94.0      # inherited: 23 °C -> 6 points off


def test_warmest_and_coldest_use_lt(forecast_json):
    fc = Forecast.from_api(forecast_json)
    assert fc.warmest.temperature == 23.0
    assert fc.coldest.temperature == 8.0


def test_bad_forecast_response():
    with pytest.raises(APIServiceError):
        Forecast.from_api({"list": []})          # no "city"


def test_client_forecast(forecast_json):
    client = OpenWeatherClient("test-key")
    client._session = FakeSession({"Madrid": FakeResponse(200, forecast_json)})
    fc = client.forecast("Madrid")
    assert fc.city == "Madrid"


def test_client_forecast_unknown_city():
    client = OpenWeatherClient("test-key")
    client._session = FakeSession({"Atlantis": FakeResponse(404)})
    with pytest.raises(LocationNotFoundError):
        client.forecast("Atlantis")


def test_daily_outlook(forecast_json):
    outlook = analytics.forecast_daily_outlook(Forecast.from_api(forecast_json).to_dataframe())
    day1 = outlook.iloc[0]
    assert len(outlook) == 2
    assert (day1["min_temp"], day1["max_temp"]) == (10.0, 23.0)
    assert day1["max_rain_chance"] == 80
    assert day1["total_rain_mm"] == 2.5


def test_best_time_outside_skips_rain_and_night(forecast_json):
    best = analytics.best_time_outside(Forecast.from_api(forecast_json).to_dataframe())
    # 13:00 is warmer but 80 % rain; 01:00 is night -> 10:00 on day 1 wins (comfort 100)
    assert best["local_time"].hour == 10
    assert best["temperature"] == 21.0


def test_forecasts_are_never_logged(tmp_path, forecast_json):
    log = WeatherLog(tmp_path / "log.csv")
    with pytest.raises(TypeError):
        log.append(Forecast.from_api(forecast_json).points)
    assert len(log) == 0
