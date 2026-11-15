"""Weather Insights — Streamlit entry point.

Run with:  uv run streamlit run app.py
"""

from datetime import timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from app_pages import load_pages
from weather_app import analytics
from weather_app.client import OpenWeatherClient, validate_city_name
from weather_app.config import get_api_key
from weather_app.exceptions import InvalidInputError, WeatherAppError
from weather_app.matching import PRESETS, SKY_OPTIONS, CityPreferences, match_cities, match_sentence
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
EXTRA_PAGES, BROKEN_PAGES = load_pages()          # teammates' pages in app_pages/
PAGES = ["Home", "Find my city", "City profile", *[m.TITLE for m in EXTRA_PAGES],
         "Live Conditions", "Compare Locations", "Analysis Sets", "Air & Sky", "Trends",
         "5-Day Forecast", "How it works"]
page = st.sidebar.radio("View", PAGES, key="page")

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

**Find my city — match score (0-100).** Every city's latest observation is scored against
what you ask for, as a weighted average of: temperature (40 %, best at the middle of your range,
minus 10 points per °C outside it), humidity (15 %), air quality (20 %), sky (15 %) and daylight
(10 %). Parts you say you don't mind are left out; a part with no data for a city counts as half.
The code is in `src/weather_app/matching.py`.

**City rankings.** "Cleaner air than 80 % of tracked cities" means 80 % of the *other* cities had
more PM2.5 at their latest observation.
""")


# ---------------- home, find my city, city profile ----------------

MAP_COLOURS = {
    "Temperature (°C)": ("temperature", "RdYlBu_r", None),
    "Comfort (0-100)": ("comfort_index", "RdYlGn", [0, 100]),
    "Air pollution — PM2.5 (µg/m³)": ("pm2_5", "YlOrRd", [0, 75]),
    "Daylight (hours)": ("daylight_hours", "Cividis", None),
}
MEDALS = ["🥇", "🥈", "🥉"]


def go_to(page_name, city=None):
    """Button callback: switch page (and the city shown on City profile)."""
    st.session_state.page = page_name
    if city is not None:
        st.session_state.profile_city = city


def madrid_time(ts):
    return ts.tz_convert(MADRID).strftime("%d %b %Y, %H:%M")


def world_map(cities, colour_col, scale, range_color=None, title=None, height=520):
    """All cities as dots on a world map, coloured by one column, with a hover card."""
    data = cities.copy()
    data["lat"] = pd.to_numeric(data["lat"], errors="coerce")
    data["lon"] = pd.to_numeric(data["lon"], errors="coerce")
    data = data.dropna(subset=["lat", "lon", colour_col])
    hover = {"lat": False, "lon": False, "temperature": ":.1f", "humidity": ":.0f",
             "comfort_index": ":.0f", "aqi_label": True, "daylight_hours": ":.1f",
             "description": True}
    hover[colour_col] = True if colour_col not in hover else hover[colour_col]
    labels = {"temperature": "Temp (°C)", "humidity": "Humidity (%)", "comfort_index": "Comfort",
              "aqi_label": "Air", "daylight_hours": "Daylight (h)", "description": "Sky",
              "pm2_5": "PM2.5 (µg/m³)", "match_score": "Match (%)", "reason": "Why"}
    fig = px.scatter_geo(data, lat="lat", lon="lon", color=colour_col, hover_name="location",
                         hover_data=hover, labels=labels, color_continuous_scale=scale,
                         range_color=range_color, projection="natural earth", title=title)
    fig.update_traces(marker=dict(size=9, line=dict(width=0.5, color="white")))
    fig.update_geos(showcountries=True, countrycolor="rgba(128,128,128,0.4)",
                    showland=True, landcolor="rgba(128,128,128,0.15)",
                    showocean=False, showframe=False, bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=40 if title else 0, b=0))
    return fig


def match_cards(results, key):
    """The top 3 matches as cards, each with a button to its City profile."""
    cols = st.columns(3)
    for medal, col, (_, row) in zip(MEDALS, cols, results.head(3).iterrows()):
        with col.container(border=True):
            st.markdown(f"### {medal} {row['location']}")
            st.metric("Match", f"{row['match_score']:.0f} %", delta_color="off",
                      delta=f"comfort {row['comfort_index']:.0f}/100")
            st.caption(row["reason"].capitalize())
            st.button("View city profile →", key=f"{key}_{row['location']}",
                      on_click=go_to, args=("City profile", row["location"]))


def csv_bytes(df):
    return df.to_csv(index=False).encode("utf-8")


SNAPSHOT_COLUMNS = ["location", "continent", "observed_at", "temperature", "feels_like",
                    "humidity", "wind_kmh", "comfort_index", "comfort_label", "description",
                    "aqi", "aqi_label", "pm2_5", "daylight_hours", "lat", "lon"]


def show_home():
    st.title("🌤️ Weather Insights")
    st.markdown("#### Find the city whose weather fits you.")
    n_cities = history["location"].nunique() if not history.empty else 0
    st.write(f"For **travellers, remote workers and exchange students**: we compare weather, "
             f"comfort, air quality and daylight across **{n_cities} cities on every continent**, "
             "from our own growing history, and rank them against what you're looking for.")
    if history.empty:
        st.info("No data yet — go to **Live Conditions** and fetch the city sets.")
        return

    updated = analytics.last_updated(history)
    days = history["fetched_at"].dt.tz_convert(MADRID).dt.date.nunique()
    hours_ago = (pd.Timestamp.now(tz="UTC") - updated).total_seconds() / 3600
    ago = f"{hours_ago:.0f} h ago" if hours_ago < 48 else f"{hours_ago / 24:.0f} days ago"
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cities tracked", n_cities)
    c2.metric("Observations logged", f"{len(history):,}")
    c3.metric("Days of history", days)
    c4.metric("Last updated (Madrid)", updated.tz_convert(MADRID).strftime("%d %b, %H:%M"),
              ago, delta_color="off")

    st.subheader("⭐ Top 3 matches right now")
    preset = st.radio("I'm looking for…", list(PRESETS), horizontal=True, key="home_preset")
    results = match_cities(history, PRESETS[preset])
    st.caption(f"Profile: {PRESETS[preset]}")
    match_cards(results, "home")
    st.button("🔎 Customise your search", type="primary", on_click=go_to, args=("Find my city",))

    st.subheader("🗺 The world at the last update")
    choice = st.selectbox("Colour cities by", list(MAP_COLOURS), key="home_map")
    col, scale, rng = MAP_COLOURS[choice]
    st.plotly_chart(world_map(analytics.latest_by_location(history), col, scale, rng),
                    width="stretch")
    st.caption("Hover over a city for its details. Each dot is that city's latest observation.")

    st.subheader("📰 Today in numbers")
    for fact in analytics.headline_insights(history):
        st.markdown(f"- {fact}")

    st.subheader("⬇️ Get the data")
    st.write("The full history is our own dataset, built one fetch at a time — the free "
             "OpenWeatherMap tier doesn't provide history.")
    d1, d2 = st.columns(2)
    d1.download_button("Full history (CSV)", log.path.read_bytes(), "weather_history.csv",
                       "text/csv", width="stretch")
    latest = analytics.latest_by_location(history)
    d2.download_button("Latest snapshot, one row per city (CSV)",
                       csv_bytes(latest[SNAPSHOT_COLUMNS]), "weather_latest.csv", "text/csv",
                       width="stretch")


def show_finder():
    st.title("🔎 Find my city")
    st.write("Tell us the weather you want. Every tracked city gets a **match score from 0 to "
             "100** based on its latest observation.")
    if history.empty:
        st.info("No data yet — go to **Live Conditions** and fetch the city sets.")
        return

    preset = st.selectbox("Start from a profile", list(PRESETS), key="finder_preset")
    base = PRESETS[preset]
    k = preset                                   # new profile -> sliders reset to its values
    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        temp = c1.slider("Temperature (°C)", -30, 45, (int(base.min_temp), int(base.max_temp)),
                         key=f"temp_{k}")
        humidity = c1.slider("Maximum humidity (%)", 20, 100, int(base.max_humidity), 5,
                             key=f"hum_{k}")
        aqi_options = [None, 1, 2, 3, 4]
        max_aqi = c2.selectbox("Air quality", aqi_options, aqi_options.index(base.max_aqi),
                               format_func=lambda v: "Don't mind" if v is None else
                               f"{analytics.AQI_LABELS[v]} or better", key=f"aqi_{k}")
        sky = c2.radio("Sky", list(SKY_OPTIONS), list(SKY_OPTIONS).index(base.sky),
                       format_func=SKY_OPTIONS.get, horizontal=True, key=f"sky_{k}")
        daylight = c3.slider("Minimum daylight (hours)", 0.0, 16.0, float(base.min_daylight), 0.5,
                             key=f"day_{k}")
        continents = c3.multiselect("Continents (empty = everywhere)",
                                    sorted(history["continent"].unique()), key=f"cont_{k}")
    try:
        prefs = CityPreferences(temp[0], temp[1], humidity, max_aqi, sky, daylight,
                                tuple(continents))
    except InvalidInputError as e:
        st.error(str(e))
        return

    results = match_cities(history, prefs)
    if results.empty:
        st.info("No cities in the chosen continents yet.")
        return
    strong = (results["match_score"] >= 80).sum()
    st.success(f"**{strong}** of {len(results)} cities are a strong match (80 %+) for "
               f"*{prefs}*. Best: **{match_sentence(results.iloc[0])}**")
    match_cards(results, "finder")

    st.plotly_chart(world_map(results, "match_score", "Viridis", [0, 100],
                              title="Match score on the map"), width="stretch")

    st.subheader("All cities, best match first")
    table = results[["match_rank", "location", "continent", "match_score", "temperature",
                     "humidity", "aqi_label", "daylight_hours", "description"]]
    st.dataframe(table, hide_index=True, width="stretch", column_config={
        "match_rank": "Rank", "location": "City", "continent": "Continent",
        "match_score": st.column_config.ProgressColumn("Match", format="%d %%",
                                                       min_value=0, max_value=100),
        "temperature": st.column_config.NumberColumn("Temp (°C)", format="%.1f"),
        "humidity": st.column_config.NumberColumn("Humidity (%)", format="%d"),
        "aqi_label": "Air", "daylight_hours": "Daylight (h)", "description": "Sky"})
    st.download_button("⬇️ Download these results (CSV)",
                       csv_bytes(results.drop(columns=["fetched_at", "query"], errors="ignore")),
                       "city_matches.csv", "text/csv")
    with st.expander("How is the match score calculated?"):
        st.markdown("A weighted average of five parts, each from 0 to 1: **temperature** 40 % "
                    "(best at the middle of your range, −10 points per °C outside it), "
                    "**humidity** 15 %, **air quality** 20 %, **sky** 15 % and **daylight** 10 %. "
                    "Parts you don't mind about are left out, and a part with no data for a "
                    "city counts as half.")


def city_timezone(row):
    """The city's own UTC offset from the log, or Madrid if it isn't known."""
    offset = pd.to_numeric(row.get("timezone_offset"), errors="coerce")
    return MADRID if pd.isna(offset) else timezone(timedelta(seconds=int(offset)))


def show_profile():
    st.title("🏙 City profile")
    if history.empty:
        st.info("No data yet — go to **Live Conditions** and fetch the city sets.")
        return
    locations = sorted(history["location"].unique())
    if st.session_state.get("profile_city") not in locations:
        st.session_state.profile_city = "Madrid, ES" if "Madrid, ES" in locations else locations[0]
    location = st.selectbox("City", locations, key="profile_city")

    city_rows = history[history["location"] == location].sort_values("observed_at")
    row = city_rows.iloc[-1]
    tz = city_timezone(row)
    local = row["observed_at"].tz_convert(tz).strftime("%a %d %b, %H:%M")
    st.markdown(f"## {location}")
    st.caption(f"{row['continent']} · latest observation {local} local time · "
               f"{str(row['description']).capitalize()} · {len(city_rows)} observations logged")

    m = st.columns(6)
    m[0].metric("Temperature", f"{row['temperature']:.1f} °C",
                f"feels {row['feels_like']:.1f} °C", delta_color="off")
    m[1].metric("Comfort", f"{row['comfort_index']:.0f}/100", row["comfort_label"],
                delta_color="off")
    m[2].metric("Air quality", row["aqi_label"] if pd.notna(row["aqi_label"]) else "—",
                f"PM2.5 {row['pm2_5']:.0f} µg/m³" if pd.notna(row["pm2_5"]) else None,
                delta_color="off")
    m[3].metric("Daylight", f"{row['daylight_hours']:.1f} h"
                if pd.notna(row["daylight_hours"]) else "—")
    m[4].metric("Humidity", f"{row['humidity']:.0f} %")
    m[5].metric("Wind", f"{row['wind_kmh']:.0f} km/h")

    st.subheader("🌍 How it ranks worldwide")
    standing = analytics.city_standing(history, location)
    cols = st.columns(3)
    for i, (_, s) in enumerate(standing.iterrows()):
        with cols[i % 3]:
            st.progress(int(s["percent_beaten"]),
                        text=f"**{s['sentence']}** (#{s['rank']} of {s['out_of']})")

    st.subheader("📈 Our history for this city")
    series = city_rows[["observed_at", "temperature", "feels_like"]].melt(
        id_vars="observed_at", var_name="series", value_name="value")
    series["observed_at"] = series["observed_at"].dt.tz_convert(tz)
    series["series"] = series["series"].map({"temperature": "Temperature",
                                             "feels_like": "Feels like"})
    fig = px.line(series, x="observed_at", y="value", color="series", markers=True,
                  labels={"observed_at": "Local time", "value": "°C", "series": ""},
                  title="Temperature and feels-like at every observation")
    st.plotly_chart(fig, width="stretch")
    left, right = st.columns(2)
    mix = analytics.conditions_mix(city_rows)
    if not mix.empty:
        left.plotly_chart(px.pie(mix, names="weather_main", values="observations", hole=0.5,
                                 title="How often it was clear, cloudy or rainy"),
                          width="stretch")
    daily = analytics.daily_summary(history, location)
    right.dataframe(daily.rename(columns={
        "date": "Date", "observations": "Obs.", "min_temp": "Min (°C)", "max_temp": "Max (°C)",
        "mean_temp": "Mean (°C)", "daily_range": "Range (°C)", "mean_humidity": "Humidity (%)"}),
        hide_index=True, width="stretch")
    st.download_button("⬇️ Download this city's history (CSV)",
                       csv_bytes(city_rows.drop(columns=["query"], errors="ignore")),
                       f"{location.replace(', ', '_')}_history.csv", "text/csv")

    st.subheader("🔮 Next 5 days")
    query = row["query"] if pd.notna(row.get("query")) else f"{row['city']},{row['country']}"
    try:
        with st.spinner(f"Loading the forecast for {location}..."):
            forecast = load_forecast(query)
    except RuntimeError as e:          # missing API key
        st.warning(f"🔑 Forecast unavailable: {e}")
        return
    except WeatherAppError as e:       # bad city, bad key, network...
        st.warning(f"Forecast unavailable: {e}")
        return
    fc = forecast.to_dataframe()
    best = analytics.best_time_outside(fc, tz=tz)
    f1, f2, f3 = st.columns(3)
    f1.metric("Warmest moment", f"{forecast.warmest.temperature:.1f} °C",
              forecast.warmest.observed_at.astimezone(tz).strftime("%a %H:%M"), delta_color="off")
    f2.metric("Coldest moment", f"{forecast.coldest.temperature:.1f} °C",
              forecast.coldest.observed_at.astimezone(tz).strftime("%a %H:%M"), delta_color="off")
    if best is None:
        f3.metric("Best time to go outside", "—", "no dry daytime slot", delta_color="off")
    else:
        f3.metric("Best time to go outside", best["local_time"].strftime("%a %H:%M"),
                  f"comfort {best['comfort_index']:.0f}/100", delta_color="off")
    st.dataframe(analytics.forecast_daily_outlook(fc, tz=tz).rename(columns={
        "date": "Date", "min_temp": "Min (°C)", "max_temp": "Max (°C)",
        "max_rain_chance": "Max rain chance (%)", "total_rain_mm": "Total rain (mm)",
        "mean_comfort": "Avg comfort (0-100)", "conditions": "Mostly"}),
        hide_index=True, width="stretch")
    st.caption("All times are the city's local time.")


views = {
    "Home": show_home,
    "Find my city": show_finder,
    "City profile": show_profile,
    "Live Conditions": show_live,
    "Compare Locations": show_compare,
    "Analysis Sets": show_sets,
    "Trends": show_trends,
    "5-Day Forecast": show_forecast,
    "Air & Sky": show_air_sky,
    "How it works": show_about,
}
for _module in EXTRA_PAGES:
    views[_module.TITLE] = lambda m=_module: m.show(history)
for _name in BROKEN_PAGES:
    st.sidebar.warning(f"Page app_pages/{_name}.py has an error and is hidden.")
views[page]()
