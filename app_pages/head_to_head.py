"""Head to head — compare two cities side by side.  OWNER: Teammate 1 (see TEAM_TASKS.md)."""

import pandas as pd
import plotly.express as px
import streamlit as st

from weather_app import analytics
from weather_app.head_to_head import COMPARED_METRICS, NO_DATA, TIE, compare_two, verdict

TITLE = "Head to head"
READY = True           # set to True when the page is ready

DEFAULT_A = "Madrid, ES"
DEFAULT_B = "Lisbon, PT"
WIN_COLOUR = "background-color: rgba(46, 160, 67, 0.30)"     # soft green, fine in light and dark


def _fmt(value, unit, decimals=1):
    """'21.3 °C', or '—' when the value is missing (e.g. no air-quality data)."""
    if pd.isna(value):
        return "—"
    space = "" if unit.startswith("/") else " "          # "43/100" but "21.3 °C"
    return f"{value:.{decimals}f}{space}{unit}"


def _city_card(column, city, values, table, latest_row):
    """Key numbers of one city, in one of the two page columns."""
    with column:
        st.subheader(city)
        st.caption(str(latest_row.get("description", "")).capitalize())
        wins = int((table["winner"] == city).sum())
        st.metric("Categories won", f"{wins} of {len(table)}")
        m1, m2 = st.columns(2)
        m1.metric("Temperature", _fmt(values["Temperature"], "°C"),
                  f"feels {_fmt(values['Feels like'], '°C')}", delta_color="off")
        m2.metric("Comfort", _fmt(values["Comfort"], "/100", 0))
        m3, m4 = st.columns(2)
        m3.metric("PM2.5", _fmt(values["PM2.5"], "µg/m³", 0))
        m4.metric("Wind", _fmt(values["Wind"], "km/h", 0))


def _highlight_winner(row, city_a, city_b):
    """Pandas Styler helper: colour the winning value of one table row green."""
    styles = {col: "" for col in row.index}
    if row["Better"] == f"🏆 {city_a}":
        styles[city_a] = WIN_COLOUR
    elif row["Better"] == f"🏆 {city_b}":
        styles[city_b] = WIN_COLOUR
    return pd.Series(styles)


def show(history):
    st.title("⚔️ Head to head")
    st.caption("Pick two cities and see which one has better weather right now, "
               "category by category.")

    if history is None or history.empty:
        st.info("No logged cities yet. Fetch some on *Live Conditions* first.")
        return

    latest = analytics.latest_by_location(history).set_index("location")
    locations = sorted(latest.index)
    if len(locations) < 2:
        st.info("Only one city is logged so far. Fetch at least one more to compare.")
        return

    index_a = locations.index(DEFAULT_A) if DEFAULT_A in locations else 0
    others = [c for c in locations if c != locations[index_a]]
    default_b = DEFAULT_B if DEFAULT_B in others else others[0]
    left, right = st.columns(2)
    city_a = left.selectbox("City A", locations, index=index_a, key="h2h_a")
    city_b = right.selectbox("City B", locations, index=locations.index(default_b), key="h2h_b")

    if city_a == city_b:
        st.warning("You picked the same city twice. Choose two different cities to compare.")
        return

    table = compare_two(history, city_a, city_b)

    # ---- the verdict, then each city's key numbers side by side ----
    st.success(f"🏆 {verdict(table)}")
    by_metric = table.set_index("metric")
    left, right = st.columns(2)
    _city_card(left, city_a, by_metric["a"], table, latest.loc[city_a])
    _city_card(right, city_b, by_metric["b"], table, latest.loc[city_b])

    missing = table[table["winner"] == NO_DATA]
    if not missing.empty:
        st.caption(f"⚠️ Not scored (data missing for at least one city): "
                   f"{', '.join(missing['metric'])}.")

    # ---- the full comparison table, winning value in green ----
    st.subheader("📋 Category by category")
    shown = table.rename(columns={"metric": "Metric", "unit": "Unit", "rule": "How we judge",
                                  "a": city_a, "b": city_b, "winner": "Better"})
    # .where(condition, other): keep the value where condition is True, else use `other`
    is_city = ~shown["Better"].isin([TIE, NO_DATA])
    shown["Better"] = shown["Better"].where(~is_city, "🏆 " + shown["Better"])
    styled = (shown[["Metric", city_a, city_b, "Unit", "Better", "How we judge"]]
              .style.apply(_highlight_winner, axis=1, city_a=city_a, city_b=city_b)
              .format({city_a: "{:.1f}", city_b: "{:.1f}"}, na_rep="no data"))
    st.dataframe(styled, hide_index=True, width="stretch")
    st.caption(f"Each city's latest observation. For temperature and feels like, closer to "
               f"21 °C wins. Values are compared to one decimal, so equal values are a tie. "
               f"{len(COMPARED_METRICS)} categories in total.")

    # ---- temperature over time for both cities ----
    st.subheader("📈 Temperature over time")
    series = analytics.trend(history, [city_a, city_b], "temperature")
    fig = px.line(series, x="observed_at", y="temperature", color="location", markers=True,
                  labels={"observed_at": "Time (Madrid)", "temperature": "Temperature (°C)",
                          "location": "City"},
                  title=f"{city_a} vs {city_b}: every logged observation")
    st.plotly_chart(fig, width="stretch")
