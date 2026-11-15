"""Data quality: the comfort index checked by hand, city presets and the names we show."""

import re

import pandas as pd
import pytest

from weather_app import analytics
from weather_app.models import comfort_index, comfort_label
from weather_app.regions import CITY_SETS, WORLD_CAPITALS, continent_of, set_cities


def history(rows):
    """Hand-made log rows (query, city, country) -> history with derived columns."""
    df = pd.DataFrame(rows, columns=["query", "city", "country"])
    df["observed_at"] = pd.to_datetime("2026-11-15T12:00Z", utc=True)
    df["fetched_at"] = df["observed_at"]
    df["temperature"] = df["feels_like"] = 20.0
    df["humidity"] = 50
    df["wind_speed"] = 2.0
    return analytics.add_derived_metrics(df)


# ---------- comfort index, worked out on paper ----------

# Real row from data/weather_log.csv (Madrid, fetched 2026-11-15 13:43 UTC):
#   temperature 12.75 °C, humidity 87 %, wind 7.72 m/s
# By hand, with the README formula:
#   temperature: 3 * |12.75 - 21|  = 3 * 8.25  = 24.75
#   humidity:    0.5 * (87 - 60)   = 0.5 * 27  = 13.50
#   wind:        4 * (7.72 - 3)    = 4 * 4.72  = 18.88
#   100 - 24.75 - 13.50 - 18.88 = 42.87 -> 42.9, "Mixed"

def test_comfort_index_matches_hand_calculation():
    assert comfort_index(12.75, 87, 7.72) == pytest.approx(42.87)
    assert comfort_label(42.87) == "Mixed"


def test_comfort_index_in_history_matches_hand_calculation():
    df = history([("Madrid,ES", "Madrid", "ES")])
    df = df.assign(temperature=12.75, humidity=87.0, wind_speed=7.72)
    row = analytics.add_derived_metrics(df).iloc[0]
    assert row["comfort_index"] == 42.9
    assert row["comfort_label"] == "Mixed"


# ---------- city presets ----------

def test_palau_uses_a_capital_the_api_knows():
    # "Ngerulmud,PW" returns 404; Ngerulmud lies in Melekeok State, which the API accepts.
    assert "Melekeok,PW" in WORLD_CAPITALS["Oceania"]
    all_cities = {city for name in CITY_SETS for city in set_cities(name)}
    assert "Ngerulmud,PW" not in all_cities
    assert continent_of("PW") == "Oceania"


def test_every_preset_city_has_a_country_code():
    pattern = re.compile(r"^[^,]+,[A-Z]{2}$")
    for name in CITY_SETS:
        bad = [city for city in set_cities(name) if not pattern.match(city)]
        assert bad == [], f"{name}: {bad}"


def test_one_capital_per_country():
    codes = [city.rsplit(",", 1)[1] for cities in WORLD_CAPITALS.values() for city in cities]
    assert len(codes) == len(set(codes))


# ---------- location: the name we asked for, not the API's ----------

@pytest.mark.parametrize("query, api_city, expected", [
    ("Tunis,TN", "Tunisia", "Tunis"),
    ("Zagreb,HR", "Donji grad", "Zagreb"),
    ("Paramaribo,SR", "Distrikt Paramaribo", "Paramaribo"),
    ("Murmansk,RU", "Murmansk Oblast", "Murmansk"),
    ("new york", "New York", "New York"),             # same name: the API's capitals
    ("Brasilia,BR", "Brasília", "Brasília"),          # same name apart from accents: keep the API's
    ("saint john's,AG", "St John's", "Saint John's"),   # not "Saint John'S" like str.title()
    (None, "Madrid", "Madrid"),                       # no query: fall back to the API's city
    ("", "Madrid", "Madrid"),
    (float("nan"), "Madrid", "Madrid"),               # how pandas stores a missing query
])
def test_display_city(query, api_city, expected):
    assert analytics.display_city(query, api_city) == expected


def test_location_uses_query_name():
    df = history([
        ("Tunis,TN", "Tunisia", "TN"),
        ("Zagreb,HR", "Donji grad", "HR"),
        ("Paramaribo,SR", "Distrikt Paramaribo", "SR"),
        ("Murmansk,RU", "Murmansk Oblast", "RU"),
    ])
    assert list(df["location"]) == ["Tunis, TN", "Zagreb, HR", "Paramaribo, SR", "Murmansk, RU"]
    assert list(df["city"]) == ["Tunisia", "Donji grad", "Distrikt Paramaribo", "Murmansk Oblast"]


def test_same_city_typed_differently_is_one_location():
    df = history([
        ("london", "London", "GB"),
        ("London,GB", "London", "GB"),
        ("Bogotá,CO", "Bogota", "CO"),
        ("Bogota,CO", "Bogota", "CO"),
    ])
    assert set(df["location"]) == {"London, GB", "Bogota, CO"}


def test_location_without_query_or_country():
    df = history([(None, "Madrid", "ES"), ("Somewhere", "Somewhere", "")])
    assert list(df["location"]) == ["Madrid, ES", "Somewhere"]


def test_location_without_query_column():
    # Old logs and hand-made tables may not have a query column at all.
    df = history([("x", "Madrid", "ES")]).drop(columns=["query", "location"])
    assert analytics.add_derived_metrics(df)["location"].iloc[0] == "Madrid, ES"
