"""About & plans — who the product is for and how it makes money.  OWNER: Teammate 3."""

import pandas as pd
import streamlit as st

from weather_app import analytics

TITLE = "About & plans"
READY = True           # set to True when the page is ready

MADRID = "Europe/Madrid"

PERSONAS = [
    ("🧳", "The traveller", "Ana, 29, has a long weekend and a cheap-flights app open.",
     "Where in Europe will it be sunny and 20-25 °C this weekend?"),
    ("💻", "The remote worker", "Marc, 34, can work from anywhere for a month.",
     "Which city has mild weather, clean air and long days right now?"),
    ("🎓", "The exchange student", "Lena, 21, is choosing between three partner universities.",
     "How do these cities really compare, day after day, not just today?"),
]

DIFFERENCES = [
    ("📈 Our own history", "The free weather API only gives *today*. We log every fetch, so we "
     "can show trends and comparisons no free app has."),
    ("🌍 Hundreds of cities at once", "Every national capital and more, compared side by side "
     "instead of one search at a time."),
    ("😷 Air quality and daylight", "PM2.5, an air-quality label and hours of daylight, next "
     "to the temperature: what actually decides whether a place is pleasant."),
    ("🎯 A match score", "Describe the weather you want and every city gets a 0-100 score with "
     "a one-line reason."),
]

PLANS = [
    ("Free", "€0", "For anyone curious", [
        "Home: top matches and world map",
        "Find my city with the preset profiles",
        "Latest conditions for every city",
    ], False),
    ("Pro", "€4 / month", "For travellers, nomads and students", [
        "Everything in Free",
        "Full history and trends",
        "City profiles and 5-day forecast",
        "Head to head and Trip planner",
        "Weather and air-quality alerts",
    ], True),
    ("Business", "From €99 / month", "For travel agencies, relocation firms, universities", [
        "Data downloads and API access",
        "Custom city lists and reports",
        "White-label city comparisons",
        "Priority support",
    ], False),
]

ROADMAP = [
    ("Next", "Automatic data collection several times a day, so the history grows on its own."),
    ("Next", "Weather and air-quality alerts (\"tell me when Lisbon is above 22 °C\")."),
    ("Later", "More cities beyond capitals: beach towns, ski resorts, university cities."),
    ("Later", "A mobile-friendly layout."),
]


def live_numbers(history):
    """Headline numbers from the log: cities, observations, days, cities with air data."""
    if history is None or history.empty:
        return {"cities": 0, "observations": 0, "days": 0, "with_air": 0, "updated": None}
    fetched = pd.to_datetime(history["fetched_at"], utc=True)
    latest = analytics.latest_by_location(history)
    with_air = (pd.to_numeric(latest["pm2_5"], errors="coerce").notna().sum()
                if "pm2_5" in latest else 0)
    return {
        "cities": history["location"].nunique(),
        "observations": len(history),
        "days": fetched.dt.tz_convert(MADRID).dt.date.nunique(),
        "with_air": int(with_air),
        "updated": analytics.last_updated(history),
    }


def show(history):
    st.title("💼 About & plans")
    st.caption("Why Weather Insights exists, who it is for and how it could pay for itself.")

    st.header("The problem")
    st.write("Weather apps show **one city at a time** and only **today**. If you are deciding "
             "*where* to go, you end up opening ten tabs, and you still can't tell whether a "
             "city is usually like this or just lucky today. Air quality and daylight are hidden "
             "in other apps, if they are there at all.")

    st.header("Who it's for")
    for col, (icon, name, who, question) in zip(st.columns(3), PERSONAS):
        with col.container(border=True):
            st.subheader(f"{icon} {name}")
            st.caption(who)
            st.write(f"*“{question}”*")

    st.header("What makes us different")
    numbers = live_numbers(history)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cities tracked", numbers["cities"])
    c2.metric("Observations logged", f"{numbers['observations']:,}")
    c3.metric("Days of history", numbers["days"])
    c4.metric("Cities with air quality", numbers["with_air"])
    if numbers["updated"] is not None:
        st.caption("Data last updated: "
                   f"{numbers['updated'].tz_convert(MADRID).strftime('%d %b %Y, %H:%M')} "
                   "(Madrid time). These numbers are live and grow with every fetch.")
    else:
        st.info("No data logged yet. Fetch some cities on *Live Conditions* first.")
    for col, (title, text) in zip(st.columns(2) * 2, DIFFERENCES):
        with col.container(border=True):
            st.markdown(f"**{title}**")
            st.write(text)

    st.header("Plans")
    for col, (name, price, audience, features, highlight) in zip(st.columns(3), PLANS):
        with col.container(border=True):
            st.subheader(f"{name} ⭐" if highlight else name)
            st.markdown(f"### {price}")
            st.caption(audience)
            st.markdown("\n".join(f"- {f}" for f in features))
    st.caption("Prices are a proposal: Pro is set between a streaming subscription and a coffee. "
               "Business is priced per organisation, because our history is data they can't "
               "get for free anywhere else.")

    st.header("Roadmap")
    for when, item in ROADMAP:
        st.markdown(f"- **{when}:** {item}")
