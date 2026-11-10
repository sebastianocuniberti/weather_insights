"""Continent presets, continent analytics and fetch progress."""

import pandas as pd
import pytest

from weather_app import analytics
from weather_app.client import OpenWeatherClient, validate_city_name
from weather_app.regions import CONTINENTS, cities_for, continent_of
from test_client import FakeResponse, FakeSession

# ---------- regions ----------

def test_every_preset_city_passes_validation():
    for city in cities_for("all"):
        assert validate_city_name(city) == city


def test_presets_fit_free_rate_limit():
    assert len(cities_for("all")) <= 60          # free tier: 60 requests per minute
    assert all(len(cities) == 7 for cities in CONTINENTS.values())


def test_cities_for_specific_and_unknown():
    assert cities_for(["Oceania"])[0] == "Sydney,AU"
    with pytest.raises(ValueError):
        cities_for(["Atlantis"])


def test_continent_of():
    assert continent_of("ES") == "Europe"
    assert continent_of("br") == "South America"
    assert continent_of("ZZ") == "Other"
    assert continent_of(None) == "Other"


# ---------- continent analytics ----------

def test_continent_summary():
    df = pd.DataFrame({
        "observed_at": pd.to_datetime(["2026-10-31T12:00Z"] * 4, utc=True),
        "city": ["Madrid", "Oslo", "Tokyo", "Seoul"],
        "country": ["ES", "NO", "JP", "KR"],
        "temperature": [20.0, 4.0, 16.0, 10.0],
        "feels_like": [20.0, 1.0, 16.0, 9.0],
        "humidity": [50, 70, 60, 40],
        "wind_speed": [1.0, 6.0, 2.0, 3.0],
    })
    summary = analytics.continent_summary(analytics.add_derived_metrics(df))
    europe = summary.set_index("continent").loc["Europe"]
    assert europe["cities"] == 2
    assert europe["avg_temp"] == 12.0
    assert europe["warmest"] == "Madrid, ES"
    assert europe["coldest"] == "Oslo, NO"
    assert list(summary["continent"]) == ["Asia", "Europe"]   # 13.0 °C vs 12.0 °C


# ---------- progress callback ----------

def test_fetch_many_reports_progress(madrid_json):
    client = OpenWeatherClient("test-key")
    client._session = FakeSession({"Madrid": FakeResponse(200, madrid_json),
                                   "Atlantis": FakeResponse(404)})
    calls = []
    client.fetch_many(["Madrid", "Atlantis"], on_progress=lambda d, t, c: calls.append((d, t, c)))
    assert calls == [(0, 2, "Madrid"), (1, 2, "Atlantis")]
