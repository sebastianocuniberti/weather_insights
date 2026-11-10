from datetime import datetime, timezone

from weather_app.models import WeatherSnapshot
from weather_app.storage import WeatherLog


def snap(city, temp, hour):
    return WeatherSnapshot(
        city=city, country="ES", temperature=temp, feels_like=temp, humidity=50,
        wind_speed=1, observed_at=datetime(2026, 10, 31, hour, tzinfo=timezone.utc),
    )


def test_empty_log(tmp_path):
    log = WeatherLog(tmp_path / "log.csv")
    assert len(log) == 0
    assert log.load().empty


def test_append_and_load_roundtrip(tmp_path):
    log = WeatherLog(tmp_path / "log.csv")
    assert log.append([snap("Madrid", 20, 10), snap("Sevilla", 25, 10)]) == 2
    assert log.append([snap("Madrid", 22, 11)]) == 1
    df = log.load()
    assert len(log) == 3
    assert list(df["temperature"]) == [20, 25, 22]
    assert str(df["observed_at"].dt.tz) == "UTC"


def test_duplicates_are_skipped(tmp_path):
    log = WeatherLog(tmp_path / "log.csv")
    log.append([snap("Madrid", 20, 10)])
    assert log.append([snap("Madrid", 20, 10)]) == 0
    assert len(log) == 1
