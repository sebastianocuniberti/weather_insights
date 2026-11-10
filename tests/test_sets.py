"""Analysis sets, batch planning, the rate limiter and set analytics."""

import pandas as pd
import pytest

from weather_app import analytics
from weather_app.client import APIClient, OpenWeatherClient, validate_city_name
from weather_app.models import WeatherSnapshot
from weather_app.regions import CITY_SETS, continent_of, plan_batches, set_cities
from weather_app.storage import WeatherLog
from test_client import FakeResponse


# ---------- the preset sets ----------

def test_every_set_city_is_valid_and_has_a_continent():
    for name in CITY_SETS:
        cities = set_cities(name)
        if name != "World capitals":   # the big set relies on the rate limiter instead
            assert len(cities) <= OpenWeatherClient.FREE_PLAN_CALLS_PER_MINUTE
        for city in cities:
            assert validate_city_name(city) == city
            assert continent_of(city.split(",")[1]) != "Other", city


def test_plan_batches_fetches_shared_cities_once():
    batches = plan_batches(["Hot vs cold", "Humid vs dry"])
    hot_cold, humid_dry = batches[0][1], batches[1][1]
    assert "Phoenix,US" in hot_cold and "Phoenix,US" not in humid_dry   # fetched in batch 1
    all_cities = [c for _, b in batches for c in b]
    assert len(all_cities) == len(set(all_cities))
    with pytest.raises(ValueError):
        set_cities("Atlantis")


# ---------- rate limiter (fake clock: no real waiting) ----------

class AlwaysOK:
    """Session that answers every request with 200 and counts the calls."""
    def __init__(self):
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return FakeResponse(200, {"ok": True})


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def limited_client(max_per_minute):
    client = APIClient("https://example.com", "key", max_calls_per_minute=max_per_minute)
    client._session = AlwaysOK()
    clock = FakeClock()
    client._clock, client._sleep = clock, clock.sleep
    return client, clock


def test_rate_limiter_pauses_after_the_limit():
    client, clock = limited_client(3)
    for _ in range(3):
        client._get("x")                 # 3 calls at t=0: no waiting
        clock.now += 1
    assert clock.slept == []
    client._get("x")                     # 4th call within the same minute -> waits
    assert len(clock.slept) == 1
    assert 56 < clock.slept[0] < 58      # until the first call is 60 s old (+0.5 s margin)
    assert client._session.calls == 4    # the request still happened after the pause


def test_rate_limiter_no_wait_when_spread_out():
    client, clock = limited_client(2)
    for _ in range(5):
        client._get("x")
        clock.now += 31                  # 2 calls per 62 s: always under the limit
    assert clock.slept == []


def test_rate_limiter_reports_wait():
    client, clock = limited_client(1)
    waits = []
    client.on_wait = waits.append
    client._get("x")
    client._get("x")
    assert waits and waits[0] == clock.slept[0]


def test_openweather_client_defaults_to_free_plan_limit():
    assert OpenWeatherClient("k").max_calls_per_minute == 55
    assert APIClient("https://x.com", "k").max_calls_per_minute is None


# ---------- storage: Namibia ----------

def test_namibia_country_code_is_not_read_as_missing(tmp_path):
    log = WeatherLog(tmp_path / "log.csv")
    log.append([WeatherSnapshot("Windhoek", "NA", 25, 24, 20, 3)])
    assert log.load().loc[0, "country"] == "NA"


# ---------- set analytics ----------

def make_history():
    rows = [
        # fetched (UTC),   query,              city,         country, temp, hum, wind
        ("10:00", "Dubai,AE",           "Dubai",          "AE", 35.0, 40, 3.0),
        ("10:01", "Riyadh,SA",          "Riyadh",         "SA", 33.0, 15, 4.0),
        ("10:01", "Reykjavik,IS",       "Reykjavik",      "IS", 2.0, 80, 9.0),
        ("10:02", "Madrid,ES",          "Madrid",         "ES", 18.0, 50, 2.0),
        ("10:02", "Seville,ES",         "Seville",        "ES", 24.0, 45, 1.0),
        ("10:02", "Bilbao,ES",          "Bilbao",         "ES", 14.0, 85, 3.0),
        ("14:00", "Dubai,AE",           "Dubai",          "AE", 37.0, 35, 3.0),
        ("14:00", "Reykjavik,IS",       "Reykjavik",      "IS", 4.0, 75, 8.0),
        ("14:01", "Madrid",             "Madrid",         "ES", 22.0, 40, 2.0),   # typed plainly
        ("14:01", "Paris,FR",           "Paris",          "FR", 15.0, 60, 2.0),   # in no analysis set
    ]
    df = pd.DataFrame(rows, columns=["t", "query", "city", "country", "temperature",
                                     "humidity", "wind_speed"])
    df["fetched_at"] = pd.to_datetime("2026-10-31 " + df.pop("t") + "Z", utc=True)
    df["observed_at"] = df["fetched_at"]
    df["feels_like"] = df["temperature"]
    return analytics.add_derived_metrics(df)


def test_tag_set_matches_by_query_and_by_city():
    tagged = analytics.tag_set(make_history(), "Spain vs Madrid")
    assert set(tagged["location"]) == {"Madrid, ES", "Seville, ES", "Bilbao, ES"}
    assert set(tagged.loc[tagged["city"] == "Madrid", "group"]) == {"Madrid"}  # both rows
    assert "Paris, FR" not in set(analytics.tag_set(make_history(), "Hot vs cold")["location"])


def test_set_comparison_uses_latest_values():
    summary = analytics.set_comparison(make_history(), "Hot vs cold").set_index("group")
    assert list(summary.index) == ["Hot", "Cold"]            # the set's own order
    assert summary.loc["Hot", "cities"] == 2
    assert summary.loc["Hot", "avg_temp"] == 35.0            # Dubai 37 (latest) + Riyadh 33
    assert summary.loc["Cold", "avg_temp"] == 4.0            # Reykjavik's latest


def test_fetch_rounds_split_on_gaps():
    times = pd.Series(pd.to_datetime(["2026-10-31 10:00", "2026-10-31 10:02",
                                      "2026-10-31 14:00", "2026-10-31 14:01"], utc=True))
    assert list(analytics.fetch_rounds(times)) == [0, 0, 1, 1]


def test_set_trend_one_point_per_round_and_group():
    trend_df = analytics.set_trend(make_history(), "Hot vs cold")
    assert len(trend_df) == 4                                 # 2 rounds x 2 groups
    first_hot = trend_df[(trend_df["group"] == "Hot")].iloc[0]
    assert first_hot["temperature"] == 34.0                   # (35 + 33) / 2
    assert first_hot["cities"] == 2


def test_difference_vs_madrid():
    tagged = analytics.tag_set(make_history(), "Spain vs Madrid")
    diff = analytics.difference_vs_reference(tagged, "Madrid, ES").set_index("location")
    assert diff.loc["Seville, ES", "difference"] == 2.0       # 24 vs Madrid's latest 22
    assert diff.loc["Bilbao, ES", "difference"] == -8.0
    assert analytics.difference_vs_reference(tagged, "Nowhere, XX") is None


def test_empty_history():
    empty = make_history().iloc[0:0]
    assert analytics.set_comparison(empty, "Hemispheres").empty
    assert analytics.set_trend(empty, "Hemispheres").empty
