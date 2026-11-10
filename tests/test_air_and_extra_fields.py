"""Extra weather fields, air quality, the log-file upgrade, capitals and Air & Sky analytics."""

import csv
from datetime import datetime, timezone

import pandas as pd
import pytest

from weather_app import analytics
from weather_app.client import OpenWeatherClient
from weather_app.exceptions import APIServiceError, InvalidAPIKeyError
from weather_app.models import AirQuality, WeatherSnapshot
from weather_app.regions import WORLD_CAPITALS, set_cities
from weather_app.storage import WeatherLog
from test_client import FakeResponse

# 2026-10-31 12:00 UTC
NOON = 1793448000


@pytest.fixture
def full_json(madrid_json):
    """Madrid with every optional field the API can send."""
    madrid_json.update({
        "dt": NOON,
        "weather": [{"id": 500, "main": "Rain", "description": "light rain"}],
        "wind": {"speed": 2.0, "deg": 270, "gust": 5.0},
        "visibility": 8000,
        "rain": {"1h": 0.6},
        "timezone": 3600,
        "sys": {"country": "ES", "sunrise": NOON - 5 * 3600, "sunset": NOON + 5 * 3600 + 1800},
    })
    madrid_json["main"].update({"sea_level": 1018, "grnd_level": 942})
    return madrid_json


AIR_JSON = {"coord": {"lon": -3.7, "lat": 40.4},
            "list": [{"main": {"aqi": 2},
                      "components": {"co": 230.0, "no2": 12.5, "o3": 60.1, "so2": 1.2,
                                     "pm2_5": 7.4, "pm10": 11.0, "nh3": 0.5},
                      "dt": NOON}]}


# ---------- extra weather fields ----------

def test_from_api_reads_extra_fields(full_json):
    snap = WeatherSnapshot.from_api(full_json)
    assert snap.weather_main == "Rain"
    assert (snap.wind_deg, snap.wind_gust, snap.visibility) == (270, 5.0, 8000)
    assert snap.rain_1h == 0.6
    assert snap.snow_1h == 0.0                     # missing "snow" means no snow
    assert (snap.sea_level, snap.grnd_level) == (1018, 942)
    assert snap.daylight_hours == 10.5             # 07:00 -> 17:30 UTC
    assert snap.local_time.hour == 13              # 12:00 UTC + 1 h
    assert snap.is_daytime is True


def test_missing_rain_means_zero(madrid_json):
    assert WeatherSnapshot.from_api(madrid_json).rain_1h == 0.0


def test_to_dict_matches_csv_columns_exactly(full_json):
    snap = WeatherSnapshot.from_api(full_json)
    assert list(snap.to_dict()) == WeatherSnapshot.FIELDS      # without air quality
    snap.air_quality = AirQuality.from_api(AIR_JSON)
    row = snap.to_dict()
    assert list(row) == WeatherSnapshot.FIELDS                 # with air quality
    assert (row["aqi"], row["pm2_5"]) == (2, 7.4)


# ---------- AirQuality ----------

def test_air_quality_parsing_and_label():
    aq = AirQuality.from_api(AIR_JSON)
    assert aq.aqi == 2 and aq.label == "Fair"
    assert aq.pm10 == 11.0
    assert "Fair" in str(aq)


def test_air_quality_bad_response():
    with pytest.raises(APIServiceError):
        AirQuality.from_api({"list": []})
    with pytest.raises(APIServiceError):
        AirQuality.from_api({"list": [{"main": {"aqi": 9}, "components": {}}]})


def test_air_quality_sorts_cleanest_first():
    clean, dirty = AirQuality(1, pm2_5=3), AirQuality(4, pm2_5=60)
    assert sorted([dirty, clean]) == [clean, dirty]


# ---------- client: weather + air quality ----------

class EndpointSession:
    """Fake session that answers by endpoint ('weather' or 'air_pollution')."""

    def __init__(self, weather, air):
        self.weather, self.air = weather, air
        self.calls = []

    def get(self, url, params=None, timeout=None):
        endpoint = url.rsplit("/", 1)[1]
        self.calls.append((endpoint, params))
        result = self.weather if endpoint == "weather" else self.air
        if isinstance(result, Exception):
            raise result
        return result


def client_with(weather, air):
    client = OpenWeatherClient("test-key", max_calls_per_minute=None)
    client._session = EndpointSession(weather, air)
    return client


def test_fetch_many_with_air_quality(full_json):
    client = client_with(FakeResponse(200, full_json), FakeResponse(200, AIR_JSON))
    snaps, errors = client.fetch_many(["Madrid,ES"], with_air_quality=True)
    assert errors == {}
    assert snaps[0].air_quality.label == "Fair"
    endpoint, params = client._session.calls[1]
    assert endpoint == "air_pollution"
    assert (params["lat"], params["lon"]) == (40.4165, -3.7026)   # coordinates from the weather call


def test_air_quality_failure_keeps_the_weather(full_json):
    client = client_with(FakeResponse(200, full_json), FakeResponse(503))
    snaps, errors = client.fetch_many(["Madrid,ES"], with_air_quality=True)
    assert len(snaps) == 1 and snaps[0].air_quality is None
    assert "Madrid,ES (air quality)" in errors


def test_air_quality_bad_key_stops_the_batch(full_json):
    client = client_with(FakeResponse(200, full_json), FakeResponse(401))
    snaps, errors = client.fetch_many(["Madrid,ES", "Venice,IT"], with_air_quality=True)
    assert "Skipped" in errors["Venice,IT"]


def test_without_air_quality_only_one_request(full_json):
    client = client_with(FakeResponse(200, full_json), FakeResponse(200, AIR_JSON))
    client.fetch_many(["Madrid,ES"])
    assert [c[0] for c in client._session.calls] == ["weather"]


# ---------- upgrading an old log file ----------

OLD_FIELDS = WeatherSnapshot.FIELDS[:16]      # the columns of the first version


def test_old_log_is_upgraded_without_losing_rows(tmp_path, full_json):
    path = tmp_path / "log.csv"
    old_row = {f: "" for f in OLD_FIELDS}
    old_row.update({"fetched_at": "2026-10-30T10:00:00+00:00",
                    "observed_at": "2026-10-30T10:00:00+00:00", "query": "Oslo,NO",
                    "city": "Oslo", "country": "NO", "temperature": "4.5",
                    "feels_like": "1.0", "humidity": "70", "wind_speed": "6.0",
                    "description": "overcast clouds"})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OLD_FIELDS)
        writer.writeheader()
        writer.writerow(old_row)

    log = WeatherLog(path)
    assert log.append([WeatherSnapshot.from_api(full_json)]) == 1

    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        header = rows[0].keys()
    assert list(header) == WeatherSnapshot.FIELDS
    assert len(rows) == 2
    assert all(rows[0][k] == v for k, v in old_row.items())   # old values untouched
    assert rows[0]["aqi"] == "" and rows[1]["weather_main"] == "Rain"
    df = log.load()
    assert len(df) == 2 and df["sunrise"].notna().sum() == 1


def test_old_log_loads_before_any_upgrade(tmp_path):
    path = tmp_path / "log.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OLD_FIELDS)
        writer.writeheader()
        writer.writerow({**dict.fromkeys(OLD_FIELDS, ""), "fetched_at": "2026-10-30T10:00:00+00:00",
                         "observed_at": "2026-10-30T10:00:00+00:00", "city": "Oslo",
                         "country": "NO", "temperature": "4", "feels_like": "1",
                         "humidity": "70", "wind_speed": "6"})
    df = analytics.add_derived_metrics(WeatherLog(path).load())
    assert list(df.columns[:len(WeatherSnapshot.FIELDS)]) == WeatherSnapshot.FIELDS
    assert df.loc[0, "daylight_hours"] != df.loc[0, "daylight_hours"]   # NaN, not a crash


# ---------- capitals ----------

def test_one_capital_per_country():
    codes = [c.rsplit(",", 1)[1] for cities in WORLD_CAPITALS.values() for c in cities]
    assert len(codes) == len(set(codes)) >= 190
    assert len(set_cities("World capitals")) == len(codes)


# ---------- Air & Sky analytics ----------

def sky_history():
    t = lambda h: datetime(2026, 10, 31, h, tzinfo=timezone.utc)
    rise, fall = t(7), t(17)
    rows = [
        # city,    cc,  lat,  hour, temp, main,     aqi, pm2_5
        ("Madrid", "ES", 40.4, 9,  10.0, "Clear",  2, 8.0),
        ("Madrid", "ES", 40.4, 14, 20.0, "Clear",  2, 9.0),
        ("Madrid", "ES", 40.4, 22, 8.0,  "Clouds", 3, 15.0),
        ("Delhi",  "IN", 28.6, 14, 30.0, "Haze",   5, 150.0),
        ("Sydney", "AU", -33.9, 14, 18.0, "Rain",  1, 4.0),
    ]
    df = pd.DataFrame(rows, columns=["city", "country", "lat", "hour", "temperature",
                                     "weather_main", "aqi", "pm2_5"])
    df["observed_at"] = df.pop("hour").apply(t)
    df["fetched_at"] = df["observed_at"]
    df["sunrise"], df["sunset"] = rise, fall
    df["timezone_offset"] = 3600
    df["feels_like"], df["humidity"], df["wind_speed"] = df["temperature"], 50, 2.0
    return analytics.add_derived_metrics(df)


def test_new_derived_columns():
    df = sky_history()
    assert df.loc[0, "daylight_hours"] == 10.0
    assert df.loc[0, "local_hour"] == 10
    assert list(df["is_daytime"][:3]) == [True, True, False]
    assert df.loc[4, "hemisphere"] == "South"
    assert df.loc[3, "aqi_label"] == "Very poor"


def test_conditions_mix():
    mix = analytics.conditions_mix(sky_history())
    madrid = mix[mix["location"] == "Madrid, ES"].set_index("weather_main")
    assert madrid.loc["Clear", "share"] == pytest.approx(66.7)
    assert madrid.loc["Clouds", "observations"] == 1


def test_air_quality_ranking_worst_first_and_latest():
    ranking = analytics.air_quality_ranking(sky_history())
    assert list(ranking["location"]) == ["Delhi, IN", "Madrid, ES", "Sydney, AU"]
    assert ranking.loc[1, "pm2_5"] == 15.0        # Madrid's latest reading


def test_day_night_difference():
    dn = analytics.day_night_difference(sky_history())
    assert list(dn["location"]) == ["Madrid, ES"]   # the only city seen by day AND night
    assert dn.loc[0, "day_temp"] == 15.0
    assert dn.loc[0, "night_temp"] == 8.0
    assert dn.loc[0, "difference"] == 7.0


def test_air_sky_with_no_new_data():
    old = sky_history().assign(weather_main=None, aqi=None, is_daytime=None)
    assert analytics.conditions_mix(old).empty
    assert analytics.air_quality_ranking(old).empty
    assert analytics.day_night_difference(old).empty
