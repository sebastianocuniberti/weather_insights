"""Analytical views built on the logged history (a pandas DataFrame from WeatherLog.load()).

Categories required by the brief:
- Trend over time ............ trend(), daily_summary()
- Cross-location comparison .. latest_by_location(), rank_locations(), extremes()
- Derived metrics ............ add_derived_metrics() (comfort index, feels-like delta,
                               km/h wind, daylight hours, local hour, day/night, hemisphere),
                               daily temperature range in daily_summary()
- Air & sky .................. conditions_mix(), air_quality_ranking(), day_night_difference()
All functions are pure (DataFrame in -> DataFrame out) so they are easy to test
with small hand-made tables.
"""

import pandas as pd

from .models import comfort_index, comfort_label
from .regions import CITY_SETS, continent_of, group_lookup

# Metrics the user can pick in the app: column -> (nice name, unit)
METRICS = {
    "temperature": ("Temperature", "°C"),
    "feels_like": ("Feels like", "°C"),
    "humidity": ("Humidity", "%"),
    "wind_kmh": ("Wind speed", "km/h"),
    "pressure": ("Pressure", "hPa"),
    "comfort_index": ("Comfort index", "0-100"),
    "feels_like_delta": ("Feels-like minus actual", "°C"),
    "wind_gust_kmh": ("Wind gusts", "km/h"),
    "clouds": ("Cloud cover", "%"),
    "rain_1h": ("Rain, last hour", "mm"),
    "visibility_km": ("Visibility", "km"),
    "daylight_hours": ("Daylight", "hours"),
    "aqi": ("Air quality index", "1 good - 5 very poor"),
    "pm2_5": ("PM2.5 fine particles", "µg/m³"),
}

AQI_LABELS = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very poor"}

# Columns added after the first version of the log. Hand-made test tables and old
# logs may not have them, so add_derived_metrics() fills them in as empty.
_NEWER_COLUMNS = ["query", "weather_main", "wind_gust", "visibility", "rain_1h", "snow_1h",
                  "sunrise", "sunset", "timezone_offset", "lat", "aqi", "pm2_5"]


def metric_label(column):
    """'temperature' -> 'Temperature (°C)' for chart axes."""
    name, unit = METRICS.get(column, (column, ""))
    return f"{name} ({unit})" if unit else name


def add_derived_metrics(df):
    """Add columns the API does not return directly. Returns a NEW DataFrame."""
    out = df.copy()
    for col in _NEWER_COLUMNS:
        if col not in out:
            out[col] = pd.NaT if col in ("sunrise", "sunset") else None
    derived = ["location", "continent", "comfort_index", "comfort_label", "feels_like_delta",
               "wind_kmh", "wind_gust_kmh", "visibility_km", "daylight_hours", "local_hour",
               "is_daytime", "hemisphere", "aqi_label"]
    if out.empty:
        for col in derived:
            out[col] = pd.Series(dtype=object)
        return out
    out["location"] = out["city"].where(out["country"].eq(""), out["city"] + ", " + out["country"])
    out["continent"] = out["country"].apply(continent_of)
    out["comfort_index"] = comfort_index(out["temperature"], out["humidity"], out["wind_speed"]).round(1)
    out["comfort_label"] = out["comfort_index"].apply(comfort_label)
    out["feels_like_delta"] = (out["feels_like"] - out["temperature"]).round(1)
    out["wind_kmh"] = (out["wind_speed"] * 3.6).round(1)
    out["wind_gust_kmh"] = (pd.to_numeric(out["wind_gust"]) * 3.6).round(1)
    out["visibility_km"] = (pd.to_numeric(out["visibility"]) / 1000).round(1)

    sunrise = pd.to_datetime(out["sunrise"], utc=True)
    sunset = pd.to_datetime(out["sunset"], utc=True)
    out["daylight_hours"] = ((sunset - sunrise).dt.total_seconds() / 3600).round(1)
    out["is_daytime"] = ((out["observed_at"] >= sunrise) & (out["observed_at"] <= sunset)
                         ).where(sunrise.notna() & sunset.notna())
    offset = pd.to_timedelta(pd.to_numeric(out["timezone_offset"]), unit="s")
    out["local_hour"] = (out["observed_at"] + offset).dt.hour      # NaN if offset unknown
    lat = pd.to_numeric(out["lat"])
    out["hemisphere"] = lat.apply(lambda v: None if pd.isna(v) else ("North" if v >= 0 else "South"))
    out["aqi_label"] = pd.to_numeric(out["aqi"]).map(AQI_LABELS)
    return out


# ---------------- cross-location comparison ----------------

def latest_by_location(df):
    """Most recent observation for every tracked location."""
    if df.empty:
        return df
    return (df.sort_values("observed_at")
              .groupby("location", as_index=False)
              .tail(1)
              .reset_index(drop=True))


def rank_locations(df, metric="comfort_index", ascending=False):
    """Rank locations by `metric` using each one's latest observation."""
    latest = latest_by_location(df)
    if latest.empty:
        return latest
    ranked = latest.sort_values(metric, ascending=ascending).reset_index(drop=True)
    ranked.insert(0, "rank", range(1, len(ranked) + 1))
    return ranked


def extremes(df):
    """Hottest, coldest, windiest, most/least comfortable location right now.

    Returns a dict like {"Hottest": ("Seville, ES", 31.2, "°C"), ...}.
    """
    latest = latest_by_location(df)
    if latest.empty:
        return {}
    picks = {
        "Hottest": ("temperature", "max"),
        "Coldest": ("temperature", "min"),
        "Windiest": ("wind_kmh", "max"),
        "Most comfortable": ("comfort_index", "max"),
        "Least comfortable": ("comfort_index", "min"),
    }
    result = {}
    for title, (col, how) in picks.items():
        idx = latest[col].idxmax() if how == "max" else latest[col].idxmin()
        row = latest.loc[idx]
        result[title] = (row["location"], row[col], METRICS[col][1])
    return result


def continent_summary(df):
    """One row per continent, from each location's latest observation.

    Averages temperature, humidity, wind and comfort across the continent's
    tracked cities, and names its warmest and coldest city right now.
    """
    latest = latest_by_location(df)
    if latest.empty:
        return pd.DataFrame(columns=["continent", "cities", "avg_temp", "avg_humidity",
                                     "avg_wind_kmh", "avg_comfort", "warmest", "coldest"])
    rows = []
    for continent, group in latest.groupby("continent"):
        rows.append({
            "continent": continent,
            "cities": len(group),
            "avg_temp": group["temperature"].mean(),
            "avg_humidity": group["humidity"].mean(),
            "avg_wind_kmh": group["wind_kmh"].mean(),
            "avg_comfort": group["comfort_index"].mean(),
            "warmest": group.loc[group["temperature"].idxmax(), "location"],
            "coldest": group.loc[group["temperature"].idxmin(), "location"],
        })
    return (pd.DataFrame(rows).round(1)
              .sort_values("avg_temp", ascending=False).reset_index(drop=True))


# ---------------- trend over time ----------------

def trend(df, locations, metric="temperature", tz="Europe/Madrid"):
    """Time series of `metric` for the chosen locations, timestamps in local time."""
    if df.empty:
        return df
    out = df[df["location"].isin(locations)][["observed_at", "location", metric]].copy()
    out["observed_at"] = out["observed_at"].dt.tz_convert(tz)
    return out.sort_values("observed_at").reset_index(drop=True)


def daily_summary(df, location, tz="Europe/Madrid"):
    """Per-day min / max / mean temperature and the daily range (max - min).

    Uses the min and max of everything we logged that day, so the more often the
    app is used the more accurate the range gets.
    """
    sub = df[df["location"] == location].copy()
    if sub.empty:
        return pd.DataFrame(columns=["date", "observations", "min_temp", "max_temp",
                                     "mean_temp", "daily_range", "mean_humidity"])
    sub["date"] = sub["observed_at"].dt.tz_convert(tz).dt.date
    daily = sub.groupby("date").agg(
        observations=("temperature", "size"),
        min_temp=("temperature", "min"),
        max_temp=("temperature", "max"),
        mean_temp=("temperature", "mean"),
        mean_humidity=("humidity", "mean"),
    ).reset_index()
    daily["daily_range"] = daily["max_temp"] - daily["min_temp"]
    return daily.round(1)[["date", "observations", "min_temp", "max_temp",
                           "mean_temp", "daily_range", "mean_humidity"]]


def change_vs_previous(df, location, metric="temperature"):
    """Difference between the latest and the previous logged observation, or None."""
    sub = df[df["location"] == location].sort_values("observed_at")
    if len(sub) < 2:
        return None
    return round(sub[metric].iloc[-1] - sub[metric].iloc[-2], 1)


# ---------------- forecast (5 days, 3-hour steps) ----------------

def forecast_daily_outlook(forecast_df, tz="Europe/Madrid"):
    """Summarise a Forecast.to_dataframe() table into one row per day.

    For each day: lowest/highest predicted temperature, the highest chance of
    rain in any 3-hour step, total expected rain, average comfort and the most
    frequent description.
    """
    if forecast_df.empty:
        return pd.DataFrame(columns=["date", "min_temp", "max_temp", "max_rain_chance",
                                     "total_rain_mm", "mean_comfort", "conditions"])
    df = forecast_df.copy()
    df["date"] = df["time"].dt.tz_convert(tz).dt.date
    daily = df.groupby("date").agg(
        min_temp=("temperature", "min"),
        max_temp=("temperature", "max"),
        max_rain_chance=("rain_chance", "max"),
        total_rain_mm=("rain_mm", "sum"),
        mean_comfort=("comfort_index", "mean"),
        conditions=("description", lambda s: s.mode().iloc[0]),
    ).reset_index()
    return daily.round(1)


def best_time_outside(forecast_df, tz="Europe/Madrid", start_hour=8, end_hour=21):
    """The daytime 3-hour step with the highest comfort index and <30 % rain chance.

    Returns that row as a pandas Series, or None if no step qualifies.
    """
    if forecast_df.empty:
        return None
    df = forecast_df.copy()
    df["local_time"] = df["time"].dt.tz_convert(tz)
    hours = df["local_time"].dt.hour
    candidates = df[(hours >= start_hour) & (hours <= end_hour) & (df["rain_chance"] < 30)]
    if candidates.empty:
        return None
    return candidates.loc[candidates["comfort_index"].idxmax()]


# ---------------- analysis sets (hot vs cold, humid vs dry, hemispheres, Spain) ----------------

def _normalise_query(query):
    """'Seville, ES ' -> 'seville,es' so queries typed slightly differently still match."""
    name, _, country = str(query).partition(",")
    return f"{name.strip().lower()},{country.strip().lower()}"


def tag_set(df, set_name):
    """Rows that belong to one analysis set, with a 'group' column (e.g. Hot / Cold).

    A row matches if the query we sent ("Seville,ES") is in the set, or — for
    cities fetched another way, e.g. typed as plain "Madrid" — if the city name
    and country returned by the API match a city in the set.
    """
    if df.empty:
        return df.assign(group=pd.Series(dtype=object))
    by_city = group_lookup(set_name)
    by_query = {f"{city},{country}": group for (city, country), group in by_city.items()}

    def find_group(row):
        group = by_query.get(_normalise_query(row["query"]))
        if group is None:
            group = by_city.get((str(row["city"]).lower(), str(row["country"]).lower()))
        return group

    out = df.copy()
    out["group"] = out.apply(find_group, axis=1)
    return out[out["group"].notna()].reset_index(drop=True)


def set_comparison(df, set_name):
    """Group averages for one set, using each city's latest observation.

    E.g. for "Humid vs dry": how many cities, average temperature, humidity,
    wind and comfort in the humid group vs the dry group.
    """
    tagged = tag_set(df, set_name)
    latest = latest_by_location(tagged)
    columns = ["group", "cities", "avg_temp", "avg_feels_like", "avg_humidity",
               "avg_wind_kmh", "avg_comfort"]
    if latest.empty:
        return pd.DataFrame(columns=columns)
    summary = latest.groupby("group").agg(
        cities=("location", "size"),
        avg_temp=("temperature", "mean"),
        avg_feels_like=("feels_like", "mean"),
        avg_humidity=("humidity", "mean"),
        avg_wind_kmh=("wind_kmh", "mean"),
        avg_comfort=("comfort_index", "mean"),
    ).reset_index()
    order = list(CITY_SETS[set_name])                     # keep the set's own group order
    summary["_order"] = summary["group"].map(order.index)
    return summary.sort_values("_order").drop(columns="_order").round(1)[columns]


def fetch_rounds(fetched_at, gap_minutes=15):
    """Number each 'round' of fetching: a new round starts after a 15+ minute gap.

    One click of "fetch all sets" takes ~2 minutes, so its rows all get the
    same round number even though their timestamps differ by seconds.
    """
    order = fetched_at.sort_values()
    new_round = order.diff() > pd.Timedelta(minutes=gap_minutes)
    return new_round.cumsum().reindex(fetched_at.index)


def set_trend(df, set_name, metric="temperature", tz="Europe/Madrid"):
    """Average `metric` per group for every fetch round, for a line chart over time."""
    tagged = tag_set(df, set_name)
    if tagged.empty:
        return pd.DataFrame(columns=["round_time", "group", metric, "cities"])
    tagged["round"] = fetch_rounds(tagged["fetched_at"])
    tagged["round_time"] = tagged.groupby("round")["fetched_at"].transform("min")
    trend_df = tagged.groupby(["round_time", "group"]).agg(
        value=(metric, "mean"), cities=("location", "nunique")).reset_index()
    trend_df = trend_df.rename(columns={"value": metric})
    trend_df["round_time"] = trend_df["round_time"].dt.tz_convert(tz)
    trend_df[metric] = trend_df[metric].round(1)
    return trend_df.sort_values("round_time").reset_index(drop=True)


def difference_vs_reference(df, reference, metric="temperature"):
    """How much each location differs from `reference` (latest values).

    E.g. reference="Madrid, ES": Seville +6.2 °C means Seville is 6.2 °C warmer
    than Madrid right now. Returns None if the reference has no data yet.
    """
    latest = latest_by_location(df)
    if latest.empty or reference not in set(latest["location"]):
        return None
    ref_value = latest.loc[latest["location"] == reference, metric].iloc[0]
    out = latest[latest["location"] != reference][["location", metric]].copy()
    out["difference"] = (out[metric] - ref_value).round(1)
    return out.sort_values("difference", ascending=False).reset_index(drop=True)


# ---------------- air & sky (newer columns: conditions, air quality, daylight) ----------------

def conditions_mix(df, min_observations=1):
    """For each location, the share (%) of its observations that were Clear, Clouds, Rain...

    Only rows that have a 'weather_main' value count (older log rows don't).
    """
    rows = df[df["weather_main"].notna()]
    columns = ["location", "weather_main", "observations", "share"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    counts = rows.groupby(["location", "weather_main"]).size().rename("observations").reset_index()
    totals = counts.groupby("location")["observations"].transform("sum")
    counts["share"] = (100 * counts["observations"] / totals).round(1)
    counts = counts[totals >= min_observations]
    return counts.sort_values(["location", "share"], ascending=[True, False]).reset_index(drop=True)


def air_quality_ranking(df):
    """Latest air quality per location, worst first (by AQI, then PM2.5)."""
    with_aq = df[pd.to_numeric(df["aqi"]).notna()]
    latest = latest_by_location(with_aq)
    if latest.empty:
        return latest
    latest = latest.assign(aqi=pd.to_numeric(latest["aqi"]),
                           pm2_5=pd.to_numeric(latest["pm2_5"]))
    return latest.sort_values(["aqi", "pm2_5"], ascending=False).reset_index(drop=True)


def day_night_difference(df):
    """Average temperature by day vs by night for each location, and the gap.

    Only locations with at least one daytime AND one night-time observation appear.
    """
    rows = df[df["is_daytime"].notna()].copy()
    columns = ["location", "day_temp", "night_temp", "difference", "observations"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows["period"] = rows["is_daytime"].map({True: "day_temp", False: "night_temp"})
    table = rows.pivot_table(index="location", columns="period", values="temperature",
                             aggfunc="mean")
    if not {"day_temp", "night_temp"} <= set(table.columns):
        return pd.DataFrame(columns=columns)
    table = table.dropna(subset=["day_temp", "night_temp"])
    table["difference"] = table["day_temp"] - table["night_temp"]
    table["observations"] = rows.groupby("location").size().reindex(table.index)
    return (table.reset_index()[columns].round(1)
                 .sort_values("difference", ascending=False).reset_index(drop=True))
