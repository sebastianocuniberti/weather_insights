"""Head to head: compare two cities' latest weather, metric by metric.

Pure functions (DataFrame in -> DataFrame / text out), so they are easy to test
with small hand-made tables, like the rest of analytics.py.
"""

import pandas as pd

from . import analytics
from .exceptions import InvalidInputError

IDEAL_TEMPERATURE = 21.0       # °C: for temperature and feels like, closer to this is better

# column in the history -> (name shown in the table, unit, what "better" means)
#   "higher"  = the bigger value wins        (comfort, daylight)
#   "lower"   = the smaller value wins       (humidity, wind, PM2.5)
#   "closest" = the value nearest 21 °C wins (temperature, feels like)
COMPARED_METRICS = {
    "temperature": ("Temperature", "°C", "closest"),
    "feels_like": ("Feels like", "°C", "closest"),
    "humidity": ("Humidity", "%", "lower"),
    "wind_kmh": ("Wind", "km/h", "lower"),
    "comfort_index": ("Comfort", "0-100", "higher"),
    "pm2_5": ("PM2.5", "µg/m³", "lower"),
    "daylight_hours": ("Daylight", "hours", "higher"),
}

RULE_TEXT = {
    "higher": "higher is better",
    "lower": "lower is better",
    "closest": f"closer to {IDEAL_TEMPERATURE:.0f} °C is better",
}

TIE = "Tie"
NO_DATA = "No data"


def _score(value, rule):
    """Turn a value into a score where BIGGER always means better.

    That way one comparison (score_a > score_b) works for every rule.
    Rounded to 1 decimal so 21.04 vs 21.0 counts as a tie, not a win.
    """
    if rule == "higher":
        score = value
    elif rule == "lower":
        score = -value
    else:                                       # "closest": the smaller the distance, the better
        score = -abs(value - IDEAL_TEMPERATURE)
    return round(score, 1)


def _winner(value_a, value_b, rule, city_a, city_b):
    """Name of the better city, "Tie", or "No data" if either value is missing."""
    if pd.isna(value_a) or pd.isna(value_b):
        return NO_DATA
    score_a, score_b = _score(value_a, rule), _score(value_b, rule)
    if score_a > score_b:
        return city_a
    if score_b > score_a:
        return city_b
    return TIE


def compare_two(df, city_a, city_b):
    """Compare the latest observation of two locations, one row per metric.

    `df` is the history with derived columns (analytics.add_derived_metrics).
    `city_a` / `city_b` are values of its "location" column, e.g. "Madrid, ES".

    Returns a DataFrame with columns:
        metric  nice name, e.g. "Temperature"
        unit    e.g. "°C"
        rule    what "better" means, e.g. "lower is better"
        a, b    the value for city A and city B (NaN if missing, e.g. no air-quality data)
        winner  city_a, city_b, "Tie" or "No data"

    Picking the same city twice is allowed: every metric is then a tie.
    Raises InvalidInputError if a city has no observations in `df`.
    """
    latest = analytics.latest_by_location(df)
    for city in (city_a, city_b):
        if latest.empty or city not in set(latest["location"]):
            raise InvalidInputError(f"No observations logged for {city!r}.")
    latest = latest.set_index("location")      # so latest.loc["Madrid, ES"] is Madrid's row

    rows = []
    for column, (name, unit, rule) in COMPARED_METRICS.items():
        # pd.to_numeric turns blanks / None into NaN, so missing data is always NaN
        value_a = pd.to_numeric(latest.loc[city_a].get(column), errors="coerce")
        value_b = pd.to_numeric(latest.loc[city_b].get(column), errors="coerce")
        rows.append({
            "metric": name,
            "unit": unit,
            "rule": RULE_TEXT[rule],
            "a": value_a,
            "b": value_b,
            "winner": _winner(value_a, value_b, rule, city_a, city_b),
        })
    return pd.DataFrame(rows, columns=["metric", "unit", "rule", "a", "b", "winner"])


def verdict(table):
    """One sentence summing up a compare_two() table.

    E.g. "Lisbon, PT wins 5 of 7 categories", or for a draw
    "It's a tie: both cities win 3 of 7 categories". Categories with missing
    data are mentioned at the end, e.g. "(1 without data)".
    """
    total = len(table)
    if total == 0:
        return "Nothing to compare yet."

    # value_counts() counts how often each winner appears; we drop the non-city answers
    wins = table["winner"].value_counts().drop([TIE, NO_DATA], errors="ignore")
    missing = int((table["winner"] == NO_DATA).sum())
    note = f" ({missing} without data)" if missing else ""

    if wins.empty:
        if missing == total:
            return "No winner: there is no data to compare."
        return f"No winner: the two cities are level in every category{note}."
    if len(wins) == 2 and wins.iloc[0] == wins.iloc[1]:
        return f"It's a tie: both cities win {wins.iloc[0]} of {total} categories{note}."
    # value_counts() sorts from most to least, so the first entry is the overall winner
    return f"{wins.index[0]} wins {wins.iloc[0]} of {total} categories{note}."
