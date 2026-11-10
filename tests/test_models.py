from datetime import datetime, timezone

import pytest

from weather_app.exceptions import APIServiceError
from weather_app.models import WeatherSnapshot, comfort_index, comfort_label


def make(city, temp, humidity=50, wind=1.0, minute=0):
    return WeatherSnapshot(
        city=city, country="XX", temperature=temp, feels_like=temp - 1,
        humidity=humidity, wind_speed=wind,
        observed_at=datetime(2026, 10, 31, 12, minute, tzinfo=timezone.utc),
    )


def test_comfort_index_known_values():
    # perfect day: 21 °C, 50 % humidity, no wind
    assert comfort_index(21, 50, 0) == 100
    # 22 °C, 40 %, 2 m/s -> only 3 points lost for the temperature
    assert comfort_index(22, 40, 2) == 97
    # 4 °C, 70 %, 8 m/s -> 100 - 51 - 5 - 20 = 24
    assert comfort_index(4, 70, 8) == 24
    # clipped at 0, never negative
    assert comfort_index(-20, 95, 20) == 0


def test_comfort_label_thresholds():
    assert comfort_label(85) == "Very comfortable"
    assert comfort_label(60) == "Comfortable"
    assert comfort_label(10) == "Harsh"


def test_from_api_parses_fields(madrid_json):
    snap = WeatherSnapshot.from_api(madrid_json, query="madrid")
    assert snap.city == "Madrid"
    assert snap.country == "ES"
    assert snap.temperature == 22.0
    assert snap.humidity == 40
    assert snap.description == "clear sky"
    assert snap.query == "madrid"
    assert snap.observed_at.tzinfo is not None


def test_from_api_missing_field_raises_clear_error(madrid_json):
    del madrid_json["main"]
    with pytest.raises(APIServiceError):
        WeatherSnapshot.from_api(madrid_json)


def test_properties(madrid_json):
    snap = WeatherSnapshot.from_api(madrid_json)
    assert snap.comfort_index == 97.0
    assert snap.feels_like_delta == -0.5
    assert snap.wind_kmh == 7.2
    assert snap.label == "Madrid, ES"


def test_sorted_uses_temperature():
    snaps = [make("A", 15), make("B", 5), make("C", 25)]
    assert [s.city for s in sorted(snaps)] == ["B", "A", "C"]


def test_equality_means_same_observation():
    assert make("A", 15) == make("A", 99)          # same city + same moment
    assert make("A", 15) != make("A", 15, minute=10)
    assert len({make("A", 15), make("A", 15)}) == 1  # hashable, de-duplicates


def test_str_and_repr(madrid_json):
    snap = WeatherSnapshot.from_api(madrid_json)
    assert "Madrid, ES" in str(snap)
    assert repr(snap).startswith("WeatherSnapshot('Madrid'")
