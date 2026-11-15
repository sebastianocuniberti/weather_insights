"""Trip planner: which city, and which day, is best for a trip in the next 5 days.

Works on the tables returned by `Forecast.to_dataframe()` (one row per 3-hour step),
so it needs no internet and can be tested with hand-made data.
"""

import pandas as pd

DAY_START_HOUR = 8      # only daytime steps count: that's when you're out and about
DAY_END_HOUR = 20
RAIN_PENALTY = 0.5      # day-score points lost per % of rain chance

PLAN_COLUMNS = ["city", "date", "day", "temperature", "max_temp", "rain_chance",
                "rain_mm", "comfort", "conditions", "day_score"]


def plan_trip(forecasts, utc_offsets=None):
    """One row per city per day, with a 0-100 day score.

    forecasts:   {city: Forecast.to_dataframe() table}; the `time` column is in UTC.
    utc_offsets: optional {city: seconds east of UTC} (the log's `timezone_offset`),
                 so "day" and "daytime" are the city's own local time. Missing = UTC.

    Day score formula, using only the daytime steps (08:00-20:00 local) of each day:

        day_score = average comfort index - 0.5 x highest chance of rain (%)

    clipped to 0-100. So a day with comfort 90 and a 0 % chance of rain scores 90, and
    the same day with a 60 % chance of rain scores 60. We take the *highest* chance of
    rain, not the average, because one rainy afternoon is enough to spoil a day out.
    Days with no daytime step (the partial first/last day of the forecast) are left out.

    Other columns: `temperature` = average daytime temperature, `max_temp` = daytime
    high, `rain_chance` = highest daytime chance of rain (%), `rain_mm` = total daytime
    rain, `comfort` = average daytime comfort, `conditions` = most frequent description.
    """
    utc_offsets = utc_offsets or {}
    days = []
    for city, fc in forecasts.items():
        if fc is None or fc.empty:
            continue
        df = fc.copy()
        offset = pd.to_numeric(utc_offsets.get(city), errors="coerce")
        offset = 0 if pd.isna(offset) else offset
        local = pd.to_datetime(df["time"], utc=True) + pd.to_timedelta(offset, unit="s")
        df["date"] = local.dt.date
        hours = local.dt.hour
        daytime = df[(hours >= DAY_START_HOUR) & (hours <= DAY_END_HOUR)]
        if daytime.empty:
            continue
        daily = daytime.groupby("date").agg(
            temperature=("temperature", "mean"),
            max_temp=("temperature", "max"),
            rain_chance=("rain_chance", "max"),
            rain_mm=("rain_mm", "sum"),
            comfort=("comfort_index", "mean"),
            conditions=("description", lambda s: s.mode().iloc[0] if not s.mode().empty else ""),
        ).reset_index()
        daily.insert(0, "city", city)
        days.append(daily)

    if not days:
        return pd.DataFrame(columns=PLAN_COLUMNS)
    plan = pd.concat(days, ignore_index=True)
    plan["day"] = pd.to_datetime(plan["date"]).dt.day_name()
    plan["day_score"] = (plan["comfort"] - RAIN_PENALTY * plan["rain_chance"]).clip(0, 100)
    plan = plan.sort_values(["date", "city"]).reset_index(drop=True)
    return plan[PLAN_COLUMNS].round(1)


def best_choice(plan):
    """(city, date, sentence) for the best day in the plan.

    Highest day score wins; a tie goes to the higher comfort, then the earlier day,
    then the city that comes first alphabetically, so the answer never depends on
    the order the cities were picked in. Returns (None, None, message) if the plan is empty.
    """
    if plan is None or plan.empty:
        return None, None, "No forecast available, so there is nothing to recommend yet."
    ranked = plan.sort_values(["day_score", "comfort", "date", "city"],
                              ascending=[False, False, True, True], kind="stable")
    best = ranked.iloc[0]
    sentence = (f"Go to {best['city']} on {best['day']}: {best['max_temp']:.0f} °C, "
                f"{best['rain_chance']:.0f} % chance of rain, comfort {best['comfort']:.0f}")
    return best["city"], best["date"], sentence
