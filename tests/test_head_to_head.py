"""Head to head: compare_two and verdict, on a small hand-made table."""

import pandas as pd
import pytest

from weather_app import analytics
from weather_app.exceptions import InvalidInputError
from weather_app.head_to_head import compare_two, verdict


def cities():
    rows = [
        # time (UTC),        city,      country, temp, feels, hum, wind m/s, aqi, pm2_5, daylight h
        ("2026-11-14T12:00Z", "Madrid", "ES", 30.0, 30.0, 20, 1.0, 1, 3.0, 10.0),   # older row
        ("2026-11-15T12:00Z", "Madrid", "ES", 16.0, 15.0, 70, 5.0, 2, 12.0, 9.8),
        ("2026-11-15T12:00Z", "Lisbon", "PT", 20.0, 20.0, 60, 3.0, 1, 6.0, 10.0),
        ("2026-11-15T12:00Z", "Oslo", "NO", 2.0, -1.0, 80, 6.0, None, None, 7.5),   # no air data
        # Twin vs Lisbon: 22 vs 20 °C (both 1 °C from 21), same feels like and daylight -> ties;
        # Twin has calmer wind and cleaner air, Lisbon is drier and more comfortable -> 2-2
        ("2026-11-15T12:00Z", "Twin", "XX", 22.0, 20.0, 70, 2.0, 1, 4.0, 10.0),
    ]
    df = pd.DataFrame(rows, columns=["observed_at", "city", "country", "temperature",
                                     "feels_like", "humidity", "wind_speed", "aqi", "pm2_5",
                                     "daylight"])
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df["fetched_at"] = df["observed_at"]
    sunrise = pd.Timestamp("2026-11-15T06:00Z")
    df["sunrise"] = sunrise
    df["sunset"] = sunrise + pd.to_timedelta(df.pop("daylight"), unit="h")
    return analytics.add_derived_metrics(df)


def test_one_row_per_metric_with_latest_values():
    table = compare_two(cities(), "Madrid, ES", "Lisbon, PT")
    assert list(table["metric"]) == ["Temperature", "Feels like", "Humidity", "Wind",
                                     "Comfort", "PM2.5", "Daylight"]
    temp = table.set_index("metric").loc["Temperature"]
    assert temp["a"] == 16.0                    # Madrid's LATEST row, not the older 30 °C
    assert temp["b"] == 20.0


def test_winner_rules():
    table = compare_two(cities(), "Madrid, ES", "Lisbon, PT").set_index("metric")
    assert table.loc["Temperature", "winner"] == "Lisbon, PT"     # 20 is closer to 21 than 16
    assert table.loc["Feels like", "winner"] == "Lisbon, PT"
    assert table.loc["Humidity", "winner"] == "Lisbon, PT"        # 60 < 70: lower is better
    assert table.loc["Wind", "winner"] == "Lisbon, PT"            # 10.8 < 18 km/h
    assert table.loc["Comfort", "winner"] == "Lisbon, PT"         # higher is better
    assert table.loc["PM2.5", "winner"] == "Lisbon, PT"           # 6 < 12
    assert table.loc["Daylight", "winner"] == "Lisbon, PT"        # 10.0 > 9.8 h


def test_closer_to_21_beats_higher_or_lower():
    # 22 °C (1 away from 21) beats 30 °C (9 away), even though 30 is "higher"
    df = cities()
    df.loc[df["location"] == "Oslo, NO", "temperature"] = 30.0
    table = compare_two(df, "Twin, XX", "Oslo, NO").set_index("metric")
    assert table.loc["Temperature", "winner"] == "Twin, XX"


def test_verdict_with_a_clear_winner():
    table = compare_two(cities(), "Madrid, ES", "Lisbon, PT")
    assert verdict(table) == "Lisbon, PT wins 7 of 7 categories."


def test_tie_per_metric_and_overall():
    table = compare_two(cities(), "Lisbon, PT", "Twin, XX").set_index("metric")
    # 20 and 22 °C are both 1 °C from 21 -> tie; same daylight -> tie
    assert table.loc["Temperature", "winner"] == "Tie"
    assert table.loc["Daylight", "winner"] == "Tie"
    assert table.loc["Feels like", "winner"] == "Tie"
    assert table.loc["PM2.5", "winner"] == "Twin, XX"
    assert verdict(table.reset_index()) == "It's a tie: both cities win 2 of 7 categories."


def test_missing_air_quality():
    table = compare_two(cities(), "Madrid, ES", "Oslo, NO").set_index("metric")
    assert pd.isna(table.loc["PM2.5", "b"])
    assert table.loc["PM2.5", "winner"] == "No data"
    assert table.loc["Temperature", "winner"] == "Madrid, ES"     # the rest still works
    assert verdict(table.reset_index()).endswith("(1 without data).")


def test_same_city_twice_is_all_ties():
    table = compare_two(cities(), "Lisbon, PT", "Lisbon, PT")
    assert set(table["winner"]) == {"Tie"}
    assert verdict(table) == "No winner: the two cities are level in every category."


def test_unknown_city_raises():
    with pytest.raises(InvalidInputError):
        compare_two(cities(), "Madrid, ES", "Atlantis")
    with pytest.raises(InvalidInputError):
        compare_two(cities().iloc[0:0], "Madrid, ES", "Lisbon, PT")


def test_verdict_edge_cases():
    assert verdict(compare_two(cities(), "Madrid, ES", "Lisbon, PT").iloc[0:0]) == \
        "Nothing to compare yet."
    no_data = pd.DataFrame({"winner": ["No data", "No data"]})
    assert verdict(no_data) == "No winner: there is no data to compare."
