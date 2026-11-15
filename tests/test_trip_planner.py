"""Trip planner: day scores and the recommendation, on hand-made forecast tables."""

import pandas as pd

from weather_app.trip_planner import PLAN_COLUMNS, best_choice, plan_trip


def forecast(steps):
    """A Forecast.to_dataframe()-style table from (UTC time, temp, rain %, rain mm, comfort)."""
    df = pd.DataFrame(steps, columns=["time", "temperature", "rain_chance", "rain_mm",
                                      "comfort_index"])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["feels_like"] = df["temperature"]
    df["humidity"] = 50
    df["wind_kmh"] = 5.0
    df["description"] = ["light rain" if r > 50 else "clear sky" for r in df["rain_chance"]]
    return df


# Thursday 19 and Friday 20 Nov 2026
SEVILLE = forecast([
    ("2026-11-19T09:00Z", 20.0, 0, 0.0, 88),
    ("2026-11-19T12:00Z", 24.0, 0, 0.0, 91),
    ("2026-11-19T15:00Z", 23.0, 10, 0.0, 94),
    ("2026-11-19T03:00Z", 12.0, 90, 2.0, 40),    # night: must be ignored
    ("2026-11-20T12:00Z", 22.0, 80, 3.0, 85),
])
OSLO = forecast([
    ("2026-11-19T12:00Z", 3.0, 20, 0.0, 30),
    ("2026-11-20T12:00Z", 4.0, 0, 0.0, 35),
])


# ---------------- plan_trip ----------------

def test_one_row_per_city_per_day():
    plan = plan_trip({"Seville, ES": SEVILLE, "Oslo, NO": OSLO})
    assert list(plan.columns) == PLAN_COLUMNS
    assert len(plan) == 4
    assert set(plan["day"]) == {"Thursday", "Friday"}


def test_day_score_formula_uses_daytime_only():
    plan = plan_trip({"Seville, ES": SEVILLE}).set_index("day")
    thursday = plan.loc["Thursday"]
    # daytime comfort (88 + 91 + 94) / 3 = 91; highest daytime rain chance 10 % -> 91 - 5 = 86
    assert thursday["comfort"] == 91.0
    assert thursday["rain_chance"] == 10
    assert thursday["day_score"] == 86.0
    assert thursday["max_temp"] == 24.0
    assert thursday["rain_mm"] == 0.0           # the 2 mm fell at night
    # Friday: comfort 85, 80 % chance of rain -> 85 - 40 = 45
    assert plan.loc["Friday", "day_score"] == 45.0
    assert plan.loc["Friday", "conditions"] == "light rain"


def test_day_score_is_clipped_to_0():
    stormy = forecast([("2026-11-19T12:00Z", 5.0, 100, 10.0, 20)])  # 20 - 50 < 0
    assert plan_trip({"Oslo, NO": stormy})["day_score"].iloc[0] == 0


def test_local_time_moves_steps_to_another_day_and_out_of_daytime():
    # 23:00 UTC on Thursday is 08:00 Friday in Tokyo (UTC+9): daytime, and Friday.
    tokyo = forecast([("2026-11-19T23:00Z", 15.0, 0, 0.0, 80)])
    assert plan_trip({"Tokyo, JP": tokyo})["day"].tolist() == []          # 23:00 UTC = night
    local = plan_trip({"Tokyo, JP": tokyo}, {"Tokyo, JP": 9 * 3600})
    assert local["day"].tolist() == ["Friday"]


def test_missing_offset_falls_back_to_utc():
    plan = plan_trip({"Seville, ES": SEVILLE}, {"Seville, ES": float("nan")})
    assert len(plan) == 2


def test_empty_and_night_only_forecasts():
    night = forecast([("2026-11-19T02:00Z", 10.0, 0, 0.0, 70)])
    empty = forecast([])
    plan = plan_trip({"A": night, "B": empty, "C": None})
    assert plan.empty
    assert list(plan.columns) == PLAN_COLUMNS
    assert plan_trip({}).empty


# ---------------- best_choice ----------------

def test_best_choice_picks_highest_score_with_sentence():
    city, date, sentence = best_choice(plan_trip({"Seville, ES": SEVILLE, "Oslo, NO": OSLO}))
    assert city == "Seville, ES"
    assert str(date) == "2026-11-19"
    assert sentence == "Go to Seville, ES on Thursday: 24 °C, 10 % chance of rain, comfort 91"


def test_best_choice_tie_goes_to_higher_comfort_then_earlier_day():
    # A: comfort 90, rain 20 % -> 80.  B: comfort 80, rain 0 % -> 80. Same score.
    a = forecast([("2026-11-20T12:00Z", 21.0, 20, 0.0, 90)])
    b = forecast([("2026-11-19T12:00Z", 21.0, 0, 0.0, 80)])
    assert best_choice(plan_trip({"B": b, "A": a}))[0] == "A"
    # same score and comfort: the earlier day wins, whatever order the cities come in
    c = forecast([("2026-11-19T12:00Z", 21.0, 0, 0.0, 90),
                  ("2026-11-20T12:00Z", 21.0, 0, 0.0, 90)])
    city, date, _ = best_choice(plan_trip({"C": c}))
    assert str(date) == "2026-11-19"


def test_best_choice_on_empty_plan():
    city, date, sentence = best_choice(plan_trip({}))
    assert city is None and date is None
    assert "No forecast" in sentence
