"""Trip planner — the best day and city for a trip in the next 5 days.  OWNER: Teammate 2."""

import pandas as pd
import plotly.express as px
import streamlit as st

from weather_app import OpenWeatherClient, analytics, trip_planner
from weather_app.config import get_api_key
from weather_app.exceptions import WeatherAppError

TITLE = "Trip planner"
READY = True           # set to True when the page is ready

MAX_CITIES = 3
DEFAULT_CITIES = ["Madrid, ES", "Lisbon, PT", "Seville, ES"]


@st.cache_data(ttl=600, show_spinner=False)
def load_forecast(query):
    """Cached for 10 minutes so changing the selection doesn't call the API every time."""
    return OpenWeatherClient(get_api_key()).forecast(query).to_dataframe()


def _query_for(row):
    """The exact query we logged ("Seville,ES"), or city + country for older rows."""
    if pd.notna(row.get("query")) and str(row.get("query")).strip():
        return row["query"]
    return f"{row['city']},{row['country']}"


def show(history):
    st.title("🧳 Trip planner")
    st.caption("You can travel in the next 5 days to one of a few cities. "
               "Which city, and which day?")

    if history is None or history.empty:
        st.info("No logged cities yet. Fetch some on *Live Conditions* first.")
        return

    latest = analytics.latest_by_location(history).set_index("location")
    locations = sorted(latest.index)
    defaults = [c for c in DEFAULT_CITIES if c in locations] or locations[:MAX_CITIES]
    chosen = st.multiselect(f"Cities (up to {MAX_CITIES})", locations, default=defaults,
                            max_selections=MAX_CITIES)
    if not chosen:
        st.info("Pick at least one city.")
        return

    forecasts, offsets = {}, {}
    with st.spinner("Loading forecasts..."):
        for city in chosen:
            row = latest.loc[city]
            try:
                forecasts[city] = load_forecast(_query_for(row))
                offsets[city] = row.get("timezone_offset")
            except RuntimeError as e:          # missing API key: same for every city
                st.warning(f"🔑 Forecast unavailable: {e}")
                return
            except WeatherAppError as e:       # bad city, bad key, network... skip this one
                st.warning(f"Forecast unavailable for {city}: {e}")

    plan = trip_planner.plan_trip(forecasts, offsets)
    if plan.empty:
        st.info("No forecast could be loaded for the chosen cities.")
        return

    _, _, sentence = trip_planner.best_choice(plan)
    st.success(f"✈️ {sentence}")

    plan["day_label"] = pd.to_datetime(plan["date"]).dt.strftime("%a %d %b")
    order = plan.drop_duplicates("date").sort_values("date")["day_label"]
    grid = plan.pivot(index="city", columns="day_label", values="day_score")
    grid = grid.reindex(columns=order)
    fig = px.imshow(grid, text_auto=".0f", color_continuous_scale="RdYlGn",
                    zmin=0, zmax=100, aspect="auto",
                    labels={"x": "Day", "y": "City", "color": "Day score"},
                    title="Day score by city and day (higher is better)")
    st.plotly_chart(fig, width="stretch")

    st.dataframe(plan.sort_values("day_score", ascending=False).rename(columns={
        "city": "City", "day_label": "Day", "temperature": "Avg temp (°C)",
        "max_temp": "High (°C)", "rain_chance": "Max rain chance (%)",
        "rain_mm": "Rain (mm)", "comfort": "Avg comfort (0-100)",
        "conditions": "Mostly", "day_score": "Day score"})[
        ["City", "Day", "Day score", "Avg temp (°C)", "High (°C)", "Max rain chance (%)",
         "Rain (mm)", "Avg comfort (0-100)", "Mostly"]],
        hide_index=True, width="stretch")
    st.caption("Day score = average daytime comfort (08:00-20:00, city's local time) "
               "minus 0.5 × the day's highest chance of rain, from 0 to 100. "
               "Partial days at the edges of the forecast that have no daytime hours are left out.")
