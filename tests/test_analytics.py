"""Small hand-made tables with answers we can check by hand."""

import pandas as pd

from weather_app import analytics


def history():
    rows = [
        # time (UTC),         city,    temp, feels, hum, wind m/s
        ("2026-10-30T08:00Z", "Madrid", 12.0, 11.0, 60, 1.0),
        ("2026-10-30T14:00Z", "Madrid", 22.0, 21.5, 40, 2.0),
        ("2026-10-31T08:00Z", "Madrid", 14.0, 13.0, 55, 1.0),
        ("2026-10-30T12:00Z", "Oslo", 4.0, -1.0, 70, 8.0),
        ("2026-10-31T12:00Z", "Oslo", 6.0, 2.0, 65, 5.0),
    ]
    df = pd.DataFrame(rows, columns=["observed_at", "city", "temperature", "feels_like",
                                     "humidity", "wind_speed"])
    df["observed_at"] = pd.to_datetime(df["observed_at"], utc=True)
    df["country"] = ["ES", "ES", "ES", "NO", "NO"]
    return analytics.add_derived_metrics(df)


def test_derived_metrics():
    df = history()
    assert df.loc[1, "location"] == "Madrid, ES"
    assert df.loc[1, "comfort_index"] == 97.0          # 22 °C, 40 %, 2 m/s
    assert df.loc[3, "feels_like_delta"] == -5.0       # Oslo feels 5° colder
    assert df.loc[3, "wind_kmh"] == 28.8


def test_latest_by_location():
    latest = analytics.latest_by_location(history())
    assert len(latest) == 2
    assert dict(zip(latest["location"], latest["temperature"])) == {
        "Madrid, ES": 14.0, "Oslo, NO": 6.0}


def test_rank_locations():
    ranked = analytics.rank_locations(history(), "temperature")
    assert list(ranked["location"]) == ["Madrid, ES", "Oslo, NO"]
    assert list(ranked["rank"]) == [1, 2]
    ranked = analytics.rank_locations(history(), "temperature", ascending=True)
    assert ranked.loc[0, "location"] == "Oslo, NO"


def test_extremes():
    ex = analytics.extremes(history())
    assert ex["Hottest"][0] == "Madrid, ES"
    assert ex["Coldest"][0] == "Oslo, NO"
    assert ex["Windiest"][0] == "Oslo, NO"


def test_daily_summary_range():
    daily = analytics.daily_summary(history(), "Madrid, ES")
    oct30 = daily.iloc[0]
    assert oct30["min_temp"] == 12.0
    assert oct30["max_temp"] == 22.0
    assert oct30["daily_range"] == 10.0
    assert oct30["observations"] == 2


def test_trend_filters_and_sorts():
    series = analytics.trend(history(), ["Oslo, NO"], "temperature")
    assert list(series["temperature"]) == [4.0, 6.0]
    assert str(series["observed_at"].dt.tz) == "Europe/Madrid"


def test_change_vs_previous():
    assert analytics.change_vs_previous(history(), "Madrid, ES") == -8.0
    assert analytics.change_vs_previous(history(), "Nowhere") is None


def test_empty_history_does_not_crash():
    empty = analytics.add_derived_metrics(pd.DataFrame(columns=[
        "observed_at", "city", "country", "temperature", "feels_like", "humidity", "wind_speed"]))
    assert analytics.latest_by_location(empty).empty
    assert analytics.extremes(empty) == {}
