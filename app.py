"""Weather Insights — Streamlit entry point.

Run with:  uv run streamlit run app.py
"""

from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from weather_app import analytics
from weather_app.client import OpenWeatherClient, validate_city_name
from weather_app.config import get_api_key
from weather_app.exceptions import InvalidInputError, WeatherAppError
from weather_app.regions import CITY_SETS, CONTINENTS, cities_for, plan_batches
from weather_app.storage import WeatherLog

MADRID = ZoneInfo("Europe/Madrid")
DEFAULT_CITIES = ["Madrid,ES", "Venice,IT", "London,GB", "Oslo,NO", "New York,US"]  # country codes avoid e.g. Venice, Florida

st.set_page_config(page_title="Weather Insights", page_icon="🌤️", layout="wide")

# ---------------- shared state ----------------

if "cities" not in st.session_state:
    st.session_state.cities = list(DEFAULT_CITIES)
if "last_fetch" not in st.session_state:
    st.session_state.last_fetch = None      # (snapshots, errors, new_rows)

log = WeatherLog()


def load_history():
    """Logged history with the derived metric columns added."""
    return analytics.add_derived_metrics(log.load())


def get_client():
    """Build the API client, or show a clear message if the key is missing."""
    try:
        return OpenWeatherClient(get_api_key())
    except RuntimeError as e:
        st.error(f"🔑 {e}")
        return None


# ---------------- sidebar ----------------

st.sidebar.title("🌤️ Weather Insights")
page = st.sidebar.radio(
    "View",
    ["Live Conditions", "Compare Locations", "Analysis Sets", "Air & Sky", "Trends",
     "5-Day Forecast",
     "How it works"],
)

st.sidebar.markdown("---")
st.sidebar.subheader("Tracked locations")

with st.sidebar.form("add_city", clear_on_submit=True):
    new_city = st.text_input("Add a city", placeholder="e.g. Valencia,ES")
    if st.form_submit_button("Add"):
        try:
            cleaned = validate_city_name(new_city)
            if cleaned.lower() in (c.lower() for c in st.session_state.cities):
                st.info(f"{cleaned} is already tracked.")
            else:
                st.session_state.cities.append(cleaned)
                st.success(f"Added {cleaned}. Press 'Fetch now' to load it.")
        except InvalidInputError as e:
            st.error(str(e))

with st.sidebar.expander("🌍 Add a whole continent"):
    picked = st.multiselect("Continents", list(CONTINENTS), key="continent_pick")
    if st.button("Track these cities", disabled=not picked):
        added = [c for c in cities_for(picked)
                 if c.lower() not in (t.lower() for t in st.session_state.cities)]
        st.session_state.cities.extend(added)
        st.success(f"Added {len(added)} cities.")

st.session_state.cities = st.sidebar.multiselect(
    "Currently tracking (remove with ✕)",
    options=st.session_state.cities,
    default=st.session_state.cities,
)

history = load_history()
st.sidebar.caption(
    f"📒 {len(history)} observations logged for "
    f"{history['location'].nunique() if not history.empty else 0} locations."
)


# ---------------- view 1: live conditions ----------------

def show_live():
    st.title("Live Conditions")
    st.write("Fetch current weather for your tracked locations. Every successful "
             "fetch is saved to the history log that powers the other views.")

    if st.button(f"🔄 Fetch my {len(st.session_state.cities)} tracked cities",
                 disabled=not st.session_state.cities):
        client = get_client()
        if client is not None:
            bar = st.progress(0.0, text="Starting...")

            def show_progress(done, total, city):
                bar.progress(done / total, text=f"Fetching {city} ({done + 1}/{total})")

            snapshots, errors = client.fetch_many(st.session_state.cities,
                                                  on_progress=show_progress)
            new_rows = log.append(snapshots)
            st.session_state.last_fetch = (snapshots, errors, new_rows)
            st.rerun()

    with st.container(border=True):
        st.subheader("📦 Fetch city sets")
        st.caption("Each set is fetched as one batch. The free plan allows 60 requests per "
                   "minute, so the app pauses automatically between batches when needed. "
                   "A city that is in several sets is fetched only once.")
        chosen_sets = st.multiselect("Sets to fetch", list(CITY_SETS), default=list(CITY_SETS))
        with_air = st.checkbox("Include air quality", value=True,
                               help="One extra request per city, so fetching takes about "
                                    "twice as long.")
        batches = plan_batches(chosen_sets)
        total = sum(len(cities) for _, cities in batches)
        requests_needed = total * (2 if with_air else 1)
        minutes = (requests_needed - 1) // OpenWeatherClient.FREE_PLAN_CALLS_PER_MINUTE \
            if total else 0
        eta = "under a minute" if minutes == 0 else f"about {minutes + 1} minutes"
        start = st.button(f"Fetch {len(batches)} set(s) — {total} cities, "
                          f"{requests_needed} requests, {eta}",
                          type="primary", disabled=not batches)
        if minutes:
            st.caption("⏳ Keep this page open until it finishes. Each batch is saved as "
                       "soon as it's done, so leaving early only loses the current batch.")

    if start:
        client = get_client()
        if client is not None:
            bar = st.progress(0.0, text="Starting...")
            status = st.empty()
            all_snaps, all_errors, all_new = [], {}, 0
            done_before = 0
            for b, (set_name, cities) in enumerate(batches, start=1):

                def show_progress(done, n, city, b=b, set_name=set_name, offset=done_before):
                    bar.progress((offset + done) / total,
                                 text=f"Batch {b}/{len(batches)} · {set_name} · "
                                      f"{city} ({offset + done + 1}/{total})")
                    status.empty()

                client.on_wait = lambda secs: status.info(
                    f"⏸ Pausing {secs:.0f} s — the free plan allows 60 requests per minute.")
                snaps, errors = client.fetch_many(cities, on_progress=show_progress,
                                                  with_air_quality=with_air)
                all_new += log.append(snaps)          # save each batch straight away
                all_snaps += snaps
                all_errors.update(errors)
                done_before += len(cities)
            st.session_state.last_fetch = (all_snaps, all_errors, all_new)
            st.rerun()

    if st.session_state.last_fetch is None:
        st.info("Press a fetch button to load current conditions.")
        return

    snapshots, errors, new_rows = st.session_state.last_fetch
    if len(errors) <= 3:
        for city, message in errors.items():
            st.warning(f"**{city}** skipped — {message}")
    else:
        with st.expander(f"⚠️ {len(errors)} cities were skipped — see why"):
            for city, message in errors.items():
                st.write(f"**{city}** — {message}")

    if not snapshots:
        return

    st.caption(f"Saved {new_rows} new observation(s) to the log "
               "(OpenWeatherMap updates about every 10 minutes, so repeats are skipped).")

    # With many cities, show cards only for the 8 warmest; the table below has them all.
    cards = sorted(snapshots, reverse=True)[:8]                  # warmest first, via __lt__
    if len(snapshots) > 8:
        st.caption(f"Showing the 8 warmest of {len(snapshots)} cities — all are in the table.")
    cols = st.columns(min(len(cards), 4))
    for i, snap in enumerate(cards):
        with cols[i % len(cols)]:
            change = analytics.change_vs_previous(history, snap.label)
            st.metric(
                snap.label,
                f"{snap.temperature:.1f} °C",
                delta=None if change is None else f"{change:+.1f} °C vs previous log",
            )
            extras = []
            if snap.air_quality is not None:
                extras.append(f"🌫 air {snap.air_quality.label.lower()}")
            if snap.daylight_hours is not None:
                extras.append(f"☀️ {snap.daylight_hours} h daylight")
            st.caption(f"{snap.description.capitalize()} · feels {snap.feels_like:.1f} °C · "
                       f"💧 {snap.humidity:.0f}% · 💨 {snap.wind_kmh} km/h"
                       + "".join(f" · {e}" for e in extras))
            st.progress(int(snap.comfort_index), text=f"Comfort {snap.comfort_index}/100 "
                                                      f"({snap.comfort_label})")

    table = pd.DataFrame([{
        "Location": s.label,
        "Temp (°C)": s.temperature,
        "Feels like (°C)": s.feels_like,
        "Feels-like gap (°C)": s.feels_like_delta,
        "Humidity (%)": s.humidity,
        "Wind (km/h)": s.wind_kmh,
        "Comfort (0-100)": s.comfort_index,
        "Conditions": s.description,
        "Rain last hour (mm)": s.rain_1h,
        "Daylight (h)": s.daylight_hours,
        "Air quality": s.air_quality.label if s.air_quality else None,
        "PM2.5 (µg/m³)": s.air_quality.pm2_5 if s.air_quality else None,
    } for s in snapshots])
    st.dataframe(table, hide_index=True, width="stretch")


# ---------------- view 2: compare locations ----------------

def show_compare():
    st.title("Compare Locations")
    if history.empty:
        st.info("No history yet — go to **Live Conditions** and press *Fetch now*.")
        return

    continents = sorted(history["continent"].unique())
    chosen = st.multiselect("Continents", continents, default=continents)
    view = history[history["continent"].isin(chosen)]
    if view.empty:
        st.info("Pick at least one continent.")
        return

    latest = analytics.latest_by_location(view)
    st.write(f"Based on the most recent observation of each of the "
             f"{len(latest)} logged locations.")

    picks = analytics.extremes(view)
    cols = st.columns(len(picks))
    for col, (title, (location, value, unit)) in zip(cols, picks.items()):
        col.metric(title, location, f"{value:.1f} {unit}", delta_color="off")

    metric = st.selectbox(
        "Rank by",
        list(analytics.METRICS),
        format_func=analytics.metric_label,
    )
    ascending = st.toggle("Lowest first", value=False)
    ranked = analytics.rank_locations(view, metric, ascending=ascending)

    fig = px.bar(
        ranked, x=metric, y="location", orientation="h",
        color=metric, color_continuous_scale="RdYlBu_r" if "temp" in metric or "feels" in metric else "Viridis",
        title=f"Locations ranked by {analytics.METRICS[metric][0].lower()}",
        labels={metric: analytics.metric_label(metric), "location": "Location"},
    )
    fig.update_yaxes(categoryorder="array", categoryarray=ranked["location"][::-1])
    fig.update_layout(height=max(400, 22 * len(ranked)))
    st.plotly_chart(fig, width="stretch")

    summary = analytics.continent_summary(view)
    if len(summary) > 1:
        fig3 = px.bar(
            summary, x="continent", y="avg_temp", color="avg_comfort",
            color_continuous_scale="RdYlGn", range_color=[0, 100],
            hover_data=["cities", "warmest", "coldest", "avg_humidity", "avg_wind_kmh"],
            title="Average temperature by continent (colour = average comfort)",
            labels={"continent": "Continent", "avg_temp": "Average temperature (°C)",
                    "avg_comfort": "Avg comfort (0-100)", "cities": "Cities",
                    "warmest": "Warmest", "coldest": "Coldest",
                    "avg_humidity": "Avg humidity (%)", "avg_wind_kmh": "Avg wind (km/h)"},
        )
        st.plotly_chart(fig3, width="stretch")

    fig2 = px.scatter(
        latest, x="temperature", y="humidity", size="wind_kmh", color="comfort_index",
        hover_name="location", text="location" if len(latest) <= 12 else None,
        color_continuous_scale="RdYlGn", range_color=[0, 100],
        title="Temperature vs humidity (bubble size = wind speed)",
        labels={"temperature": "Temperature (°C)", "humidity": "Humidity (%)",
                "comfort_index": "Comfort (0-100)", "wind_kmh": "Wind (km/h)"},
    )
    fig2.update_traces(textposition="top center")
    st.plotly_chart(fig2, width="stretch")

    with st.expander("Ranking table"):
        st.dataframe(
            ranked[["rank", "location", "temperature", "feels_like", "humidity",
                    "wind_kmh", "comfort_index", "comfort_label", "description"]],
            hide_index=True, width="stretch",
        )


# ---------------- view: analysis sets ----------------

SET_DESCRIPTIONS = {
    "Continents": "7 major cities per continent.",
    "Hot vs cold": "Some of the hottest and coldest inhabited places on Earth.",
    "Humid vs dry": "Tropical, humid cities against deserts and high, dry cities — "
                    "shows how humidity changes comfort at similar temperatures.",
    "Hemispheres": "Cities 30-45° north and south of the equator: similar distance from "
                   "the equator, opposite seasons.",
    "Spain vs Madrid": "Spain's main cities compared with Madrid.",
    "World capitals": "The capital of every country (196), grouped by continent.",
}


def show_sets():
    st.title("Analysis Sets")
    if history.empty:
        st.info("No history yet — go to **Live Conditions** and fetch the city sets.")
        return

    set_name = st.selectbox("Set", list(CITY_SETS))
    st.caption(SET_DESCRIPTIONS.get(set_name, ""))
    summary = analytics.set_comparison(history, set_name)
    if summary.empty:
        st.info(f"No data for this set yet — fetch **{set_name}** on Live Conditions.")
        return

    cols = st.columns(len(summary))
    for col, (_, row) in zip(cols, summary.iterrows()):
        col.metric(f"{row['group']} ({row['cities']} cities)", f"{row['avg_temp']:.1f} °C",
                   f"comfort {row['avg_comfort']:.0f}/100 · humidity {row['avg_humidity']:.0f}%",
                   delta_color="off")

    metric = st.selectbox("Metric", list(analytics.METRICS), format_func=analytics.metric_label,
                          key="set_metric")

    # 1) where every city in the set stands right now, coloured by group
    latest = analytics.latest_by_location(analytics.tag_set(history, set_name))
    latest = latest.sort_values(metric, ascending=False)
    fig = px.bar(
        latest, x=metric, y="location", color="group", orientation="h",
        title=f"{analytics.METRICS[metric][0]} now, by group",
        labels={metric: analytics.metric_label(metric), "location": "City", "group": "Group"},
    )
    fig.update_yaxes(categoryorder="array", categoryarray=latest["location"][::-1])
    fig.update_layout(height=max(400, 20 * len(latest)))
    st.plotly_chart(fig, width="stretch")

    # 2) how the groups compare over time (one point per fetch round)
    trend_df = analytics.set_trend(history, set_name, metric)
    fig2 = px.line(
        trend_df, x="round_time", y=metric, color="group", markers=True,
        hover_data=["cities"],
        title=f"Group average {analytics.METRICS[metric][0].lower()} per fetch round",
        labels={"round_time": "Fetch round (Madrid time)", metric: analytics.metric_label(metric),
                "group": "Group", "cities": "Cities"},
    )
    st.plotly_chart(fig2, width="stretch")
    if trend_df["round_time"].nunique() < 3:
        st.caption("ℹ️ Fewer than 3 fetch rounds so far — fetch a few times a day to see "
                   "the lines develop.")

    # 3) extra view for Spain: difference from Madrid
    if set_name == "Spain vs Madrid":
        tagged = analytics.tag_set(history, set_name)
        diff = analytics.difference_vs_reference(tagged, "Madrid, ES", metric)
        if diff is not None and not diff.empty:
            unit = analytics.METRICS[metric][1]
            fig3 = px.bar(
                diff, x="difference", y="location", orientation="h",
                color="difference", color_continuous_scale="RdBu_r", color_continuous_midpoint=0,
                title=f"Difference from Madrid right now ({unit})",
                labels={"difference": f"Difference from Madrid ({unit})", "location": "City"},
            )
            fig3.update_yaxes(categoryorder="array", categoryarray=diff["location"][::-1])
            st.plotly_chart(fig3, width="stretch")

    with st.expander("Group summary table"):
        st.dataframe(summary, hide_index=True, width="stretch")


# ---------------- view: air & sky ----------------

def show_air_sky():
    st.title("Air & Sky")
    st.write("Air quality, daylight, how often it rains or shines, and day vs night — from "
             "the extra data saved with every fetch since 31 Oct 2026.")
    if history.empty:
        st.info("No history yet — go to **Live Conditions** and fetch some cities.")
        return

    continents = sorted(history["continent"].unique())
    chosen = st.multiselect("Continents", continents, default=continents, key="air_continents")
    view = history[history["continent"].isin(chosen)]

    # 1) air quality
    st.subheader("🌫 Air quality right now")
    ranking = analytics.air_quality_ranking(view)
    if ranking.empty:
        st.info("No air-quality data yet — fetch with **Include air quality** ticked.")
    else:
        counts = ranking["aqi_label"].value_counts()
        cols = st.columns(5)
        for col, label in zip(cols, analytics.AQI_LABELS.values()):
            col.metric(label, int(counts.get(label, 0)), "cities", delta_color="off")
        n = st.slider("Show the most polluted", 5, max(5, len(ranking)),
                      min(20, len(ranking)), key="aq_n") if len(ranking) > 5 else len(ranking)
        top = ranking.head(n)
        fig = px.bar(
            top, x="pm2_5", y="location", orientation="h", color="aqi_label",
            category_orders={"aqi_label": list(analytics.AQI_LABELS.values())},
            color_discrete_map={"Good": "#2e7d32", "Fair": "#9ccc65", "Moderate": "#fbc02d",
                                "Poor": "#ef6c00", "Very poor": "#c62828"},
            title="Fine particles (PM2.5) — most polluted first",
            labels={"pm2_5": "PM2.5 (µg/m³)", "location": "City", "aqi_label": "Air quality"},
        )
        fig.update_yaxes(categoryorder="array", categoryarray=top["location"][::-1])
        fig.update_layout(height=max(400, 22 * len(top)))
        st.plotly_chart(fig, width="stretch")

    # 2) daylight vs latitude
    st.subheader("☀️ Daylight vs latitude")
    latest = analytics.latest_by_location(view)
    sun = latest[latest["daylight_hours"].notna()]
    if sun.empty:
        st.info("No sunrise/sunset data yet — it is saved with every new fetch.")
    else:
        fig2 = px.scatter(
            sun, x="lat", y="daylight_hours", color="hemisphere", hover_name="location",
            title="Hours of daylight today by latitude (opposite seasons in each hemisphere)",
            labels={"lat": "Latitude (° north +, south −)", "daylight_hours": "Daylight (hours)",
                    "hemisphere": "Hemisphere"},
        )
        fig2.add_vline(x=0, line_dash="dot", annotation_text="Equator")
        st.plotly_chart(fig2, width="stretch")

    # 3) how often is it rainy / cloudy / clear?
    st.subheader("🌦 How often is it clear, cloudy or rainy?")
    mix = analytics.conditions_mix(view)
    if mix.empty:
        st.info("No condition categories yet — they are saved with every new fetch.")
    else:
        totals = mix.groupby("location")["observations"].sum().sort_values(ascending=False)
        locations = st.multiselect("Cities", list(totals.index),
                                   default=list(totals.index[:12]), key="mix_cities")
        sub = mix[mix["location"].isin(locations)]
        fig3 = px.bar(
            sub, x="share", y="location", color="weather_main", orientation="h",
            hover_data=["observations"],
            title="Share of our observations in each condition",
            labels={"share": "Share of observations (%)", "location": "City",
                    "weather_main": "Condition", "observations": "Observations"},
        )
        fig3.update_layout(height=max(350, 28 * len(locations)), barmode="stack")
        st.plotly_chart(fig3, width="stretch")
        st.caption("Based on our own logged observations — more fetches at different times "
                   "of day make these shares more reliable.")

    # 4) day vs night
    st.subheader("🌗 Day vs night temperature")
    dn = analytics.day_night_difference(view)
    if dn.empty:
        st.info("Needs at least one daytime and one night-time observation of the same city "
                "— fetching at different times of day builds this up.")
    else:
        fig4 = px.bar(
            dn.head(25), x="difference", y="location", orientation="h",
            hover_data=["day_temp", "night_temp", "observations"],
            title="How much warmer days are than nights (average of our observations)",
            labels={"difference": "Day minus night (°C)", "location": "City",
                    "day_temp": "Day avg (°C)", "night_temp": "Night avg (°C)",
                    "observations": "Observations"},
        )
        fig4.update_yaxes(categoryorder="total ascending")
        st.plotly_chart(fig4, width="stretch")


# ---------------- view 3: trends ----------------

def show_trends():
    st.title("Trends Over Time")
    if history.empty:
        st.info("No history yet — go to **Live Conditions** and press *Fetch now*.")
        return

    locations = sorted(history["location"].unique())
    chosen = st.multiselect("Locations", locations, default=locations[:3])
    metric = st.selectbox("Metric", list(analytics.METRICS), format_func=analytics.metric_label)

    series = analytics.trend(history, chosen, metric)
    if series.empty:
        st.info("Pick at least one location.")
    else:
        fig = px.line(
            series, x="observed_at", y=metric, color="location", markers=True,
            title=f"{analytics.METRICS[metric][0]} over time",
            labels={"observed_at": "Time (Madrid)", metric: analytics.metric_label(metric),
                    "location": "Location"},
        )
        st.plotly_chart(fig, width="stretch")
        counts = series.groupby("location").size()
        if counts.min() < 3:
            st.caption("ℹ️ Some locations have fewer than 3 observations — fetch a few "
                       "times over the coming days to see a real trend.")

    st.markdown("---")
    st.subheader("Daily temperature range")
    location = st.selectbox("Location", locations, key="daily_loc")
    daily = analytics.daily_summary(history, location)
    if daily.empty:
        st.info("No data for this location yet.")
        return

    fig = px.bar(
        daily, x="date", y="daily_range", base="min_temp",
        hover_data=["min_temp", "max_temp", "mean_temp", "observations"],
        title=f"{location}: daily min → max temperature",
        labels={"date": "Date", "daily_range": "Daily range (°C)", "min_temp": "Min (°C)",
                "max_temp": "Max (°C)", "mean_temp": "Mean (°C)"},
    )
    fig.update_yaxes(title="Temperature (°C)")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(daily, hide_index=True, width="stretch")


# ---------------- view 4: 5-day forecast ----------------

@st.cache_data(ttl=600, show_spinner=False)
def load_forecast(city):
    """Cached for 10 minutes: the forecast doesn't change faster than that, and
    switching back and forth between cities shouldn't call the API every time."""
    return OpenWeatherClient(get_api_key()).forecast(city)


def show_forecast():
    st.title("5-Day Forecast")
    st.write("Predicted conditions in 3-hour steps from OpenWeatherMap's free forecast. "
             "Forecasts are shown here only — they are **not** added to the history log, "
             "because they are predictions, not observations.")

    if not st.session_state.cities:
        st.info("Add at least one city in the sidebar to get started.")
        return

    city = st.selectbox("City", st.session_state.cities)
    try:
        with st.spinner(f"Loading the forecast for {city}..."):
            forecast = load_forecast(city)
    except RuntimeError as e:          # missing API key
        st.error(f"🔑 {e}")
        return
    except WeatherAppError as e:       # bad city, bad key, network...
        st.error(str(e))
        return

    df = forecast.to_dataframe()
    df["time"] = df["time"].dt.tz_convert("Europe/Madrid")
    outlook = analytics.forecast_daily_outlook(forecast.to_dataframe())

    st.subheader(forecast.label)
    c1, c2, c3 = st.columns(3)
    c1.metric("Warmest moment", f"{forecast.warmest.temperature:.1f} °C",
              forecast.warmest.observed_at.astimezone(MADRID).strftime("%a %H:%M"), delta_color="off")
    c2.metric("Coldest moment", f"{forecast.coldest.temperature:.1f} °C",
              forecast.coldest.observed_at.astimezone(MADRID).strftime("%a %H:%M"), delta_color="off")
    best = analytics.best_time_outside(forecast.to_dataframe())
    if best is None:
        c3.metric("Best time to go out", "—", "no dry daytime slot", delta_color="off")
    else:
        c3.metric("Best time to go out", best["local_time"].strftime("%a %H:%M"),
                  f"comfort {best['comfort_index']:.0f}/100", delta_color="off")

    temps = df.melt(id_vars="time", value_vars=["temperature", "feels_like"],
                    var_name="series", value_name="value")
    temps["series"] = temps["series"].map({"temperature": "Temperature",
                                           "feels_like": "Feels like"})
    fig = px.line(
        temps, x="time", y="value", color="series", markers=True,
        title="Temperature and feels-like, next 5 days",
        labels={"time": "Time (Madrid)", "value": "Temperature (°C)", "series": ""},
    )
    st.plotly_chart(fig, width="stretch")

    fig2 = px.bar(
        df, x="time", y="rain_chance", color="rain_mm", color_continuous_scale="Blues",
        range_y=[0, 100],
        title="Chance of rain per 3-hour step",
        labels={"time": "Time (Madrid)", "rain_chance": "Chance of rain (%)",
                "rain_mm": "Expected rain (mm)"},
    )
    st.plotly_chart(fig2, width="stretch")

    st.subheader("Day by day")
    st.dataframe(
        outlook.rename(columns={
            "date": "Date", "min_temp": "Min (°C)", "max_temp": "Max (°C)",
            "max_rain_chance": "Max rain chance (%)", "total_rain_mm": "Total rain (mm)",
            "mean_comfort": "Avg comfort (0-100)", "conditions": "Mostly",
        }),
        hide_index=True, width="stretch",
    )


# ---------------- view 5: how it works ----------------

def show_about():
    st.title("How it works")
    st.markdown("""
**Data.** OpenWeatherMap's free tier only returns *current* conditions, one city per request.
Every time you fetch, each successful result is appended to `data/weather_log.csv` with its timestamp,
so the app builds its own history over time. Repeat observations are skipped.

**Comfort index (0-100).** Our own score — not something the API returns. Start at 100 and subtract:
- 3 points for every °C away from 21 °C,
- 0.5 points for every % of humidity outside the 40-60 % band,
- 4 points for every m/s of wind above a light breeze (3 m/s).

80+ is *very comfortable*, below 20 is *harsh*.

**Feels-like gap.** Feels-like minus actual temperature: negative means it feels colder than
the thermometer says (wind chill), positive means warmer (humidity).

**Daily range.** Highest minus lowest temperature we logged for a location on each day —
it gets more accurate the more often the app is used.

**City sets.** The API answers one city per request, so continents and the analysis sets
(hot vs cold, humid vs dry, hemispheres, Spain vs Madrid) are preset city lists in
`regions.py`. Each set is fetched as one batch; the client never makes more than 55 requests in
any 60 seconds (the free limit is 60), pausing automatically when needed. Cities in several
sets are fetched once. Extra cities you add are assigned a continent from their country code.

**Extra data per city.** Besides temperature, humidity and wind, every fetch saves the
condition category (Clear, Clouds, Rain...), rain and snow in the last hour, wind gusts and
direction, visibility, sunrise and sunset (→ hours of daylight, day or night), the city's time
zone and ground-level pressure. With *Include air quality* ticked, the app also calls the free
Air Pollution API for each city: an index from 1 (Good) to 5 (Very poor) plus PM2.5, PM10, NO₂,
O₃, SO₂ and CO. Rows saved before 31 Oct 2026 simply have these columns empty.

**World capitals.** One capital per country (196). With all sets selected the app fetches 262
unique cities; with air quality that is 524 requests, which the rate limiter spreads over
about 10 minutes.

**5-Day Forecast.** Uses OpenWeatherMap's free 3-hourly forecast. *Best time to go out* is the
daytime step (08:00-21:00) with the highest comfort index and less than 30 % chance of rain.
Forecasts are never written to the history log.
""")


views = {
    "Live Conditions": show_live,
    "Compare Locations": show_compare,
    "Analysis Sets": show_sets,
    "Trends": show_trends,
    "5-Day Forecast": show_forecast,
    "Air & Sky": show_air_sky,
    "How it works": show_about,
}
views[page]()
