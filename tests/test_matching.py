"""Find my city, city rankings and landing-page insights, on hand-made tables."""

import pandas as pd
import pytest

from weather_app import analytics
from weather_app.exceptions import InvalidInputError
from weather_app.matching import PRESETS, CityPreferences, match_cities, match_sentence


def cities():
    rows = [
        # time (UTC),        city,       country, temp, hum, wind, sky,      aqi, pm2_5, daylight h
        ("2026-11-14T12:00Z", "Lisbon", "PT", 18.0, 60, 2.0, "Clouds", 1, 8.0, 10.0),
        ("2026-11-15T12:00Z", "Lisbon", "PT", 22.0, 55, 2.0, "Clear", 1, 6.0, 10.0),
        ("2026-11-15T12:00Z", "Delhi", "IN", 24.0, 50, 1.0, "Haze", 5, 180.0, 10.9),
        ("2026-11-15T12:00Z", "Oslo", "NO", 2.0, 80, 6.0, "Rain", 1, 5.0, 7.5),
        ("2026-11-15T12:00Z", "Dakar", "SN", 30.0, 78, 4.0, "Clear", 4, 60.0, 11.5),
    ]
    df = pd.DataFrame(rows, columns=["observed_at", "city", "country", "temperature", "humidity",
                                     "wind_speed", "weather_main", "aqi", "pm2_5", "daylight"])
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df["fetched_at"] = df["observed_at"]
    df["feels_like"] = df["temperature"]
    df["description"] = df["weather_main"].str.lower()
    # sunrise/sunset 06:00 + daylight hours, so daylight_hours comes out as above
    sunrise = pd.Timestamp("2026-11-15T06:00Z")
    df["sunrise"] = sunrise
    df["sunset"] = sunrise + pd.to_timedelta(df.pop("daylight"), unit="h")
    return analytics.add_derived_metrics(df)


# ---------------- CityPreferences ----------------

def test_preferences_validation():
    with pytest.raises(InvalidInputError):
        CityPreferences(min_temp=30, max_temp=20)
    with pytest.raises(InvalidInputError):
        CityPreferences(max_humidity=120)
    with pytest.raises(InvalidInputError):
        CityPreferences(max_aqi=7)
    with pytest.raises(InvalidInputError):
        CityPreferences(sky="purple")
    with pytest.raises(InvalidInputError):
        CityPreferences(min_daylight=25)


def test_preferences_str_and_continents_tuple():
    prefs = CityPreferences(18, 26, 70, 2, "dry", 10, ["Europe"])
    assert prefs.continents == ("Europe",)
    assert str(prefs) == ("18 to 26 °C · humidity ≤ 70 % · air fair or better · "
                          "no rain or snow · ≥ 10 h daylight · in Europe")


def test_all_presets_are_valid():
    assert all(isinstance(p, CityPreferences) for p in PRESETS.values())


# ---------------- match_cities ----------------

def test_best_match_uses_latest_observation():
    results = match_cities(cities(), CityPreferences(18, 26, 70, 2, "clear", 0))
    assert results.loc[0, "location"] == "Lisbon, PT"       # 22 °C (the middle), clean, clear
    assert results.loc[0, "match_score"] == 100
    assert results.loc[0, "temperature"] == 22.0            # not the older 18 °C row
    assert list(results["match_rank"]) == [1, 2, 3, 4]


def test_pollution_lowers_the_score():
    results = match_cities(cities(), CityPreferences(18, 26, 70, 2)).set_index("location")
    # Delhi: 24 °C is inside the range (temp 0.925), humidity fine, but AQI 5 vs max 2 -> air 0
    assert results.loc["Delhi, IN", "air_fit"] == 0
    assert results.loc["Delhi, IN", "match_score"] == pytest.approx(
        100 * (40 * 0.925 + 15 * 1 + 20 * 0) / 75, abs=0.5)
    # if the user doesn't mind the air, Delhi scores much better
    relaxed = match_cities(cities(), CityPreferences(18, 26, 70, None)).set_index("location")
    assert relaxed.loc["Delhi, IN", "match_score"] > results.loc["Delhi, IN", "match_score"]
    assert "air_fit" not in relaxed


def test_temperature_outside_range_drops_10_points_per_degree():
    results = match_cities(cities(), CityPreferences(18, 26, 100, None)).set_index("location")
    # Dakar is 30 °C: 4 °C above 26 -> 0.85 * (1 - 0.4) = 0.51
    assert results.loc["Dakar, SN", "temperature_fit"] == 51


def test_dry_sky_and_daylight():
    prefs = CityPreferences(-5, 30, 100, None, "dry", 10)
    results = match_cities(cities(), prefs).set_index("location")
    assert results.loc["Oslo, NO", "sky_fit"] == 0                   # raining
    assert results.loc["Oslo, NO", "daylight_fit"] == round(100 * (1 - 2.5 / 3))
    assert results.loc["Lisbon, PT", "sky_fit"] == 100


def test_continent_filter_and_sentence():
    results = match_cities(cities(), CityPreferences(continents=("Europe",)))
    assert set(results["location"]) == {"Lisbon, PT", "Oslo, NO"}
    sentence = match_sentence(results.iloc[0])
    assert sentence.startswith("Lisbon, PT — 100 % match: 22 °C")
    assert "clean air" in sentence and "10.0 h daylight" in sentence


def test_match_empty_history():
    empty = cities().iloc[0:0]
    assert match_cities(empty, CityPreferences()).empty


# ---------------- city_standing, biggest_changes, headline_insights ----------------

def test_city_standing_sentences():
    standing = analytics.city_standing(cities(), "Lisbon, PT").set_index("metric")
    # PM2.5 6 vs others 180, 5, 60 -> cleaner than 2 of 3
    assert standing.loc["pm2_5", "sentence"] == "Cleaner air than 67 % of tracked cities"
    assert standing.loc["pm2_5", "rank"] == 2
    # 22 °C vs 24, 2, 30 -> warmer than 1 of 3
    assert standing.loc["temperature", "percent_beaten"] == 33
    assert standing.loc["temperature", "out_of"] == 4
    assert analytics.city_standing(cities(), "Atlantis").empty


def test_biggest_changes_needs_two_observations():
    changes = analytics.biggest_changes(cities())
    assert list(changes["location"]) == ["Lisbon, PT"]       # the only city logged twice
    assert changes.loc[0, "change"] == 4.0


def test_last_updated():
    assert analytics.last_updated(cities()) == pd.Timestamp("2026-11-15T12:00Z")
    assert analytics.last_updated(cities().iloc[0:0]) is None


def test_headline_insights():
    facts = analytics.headline_insights(cities())
    text = " | ".join(facts)
    assert "Hottest place we track: Dakar, SN at 30 °C" in text
    assert "Coldest place we track: Oslo, NO at 2 °C" in text
    assert "Most polluted air: Delhi, IN (PM2.5 180 µg/m³, very poor)" in text
    assert "raining in 1 cities and clear in 2" in text
    assert "Lisbon, PT is 4.0 °C warmer" in text
    assert analytics.headline_insights(cities().iloc[0:0]) == []
