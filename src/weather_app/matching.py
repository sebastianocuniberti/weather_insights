"""Find my city: score every tracked city against what the user wants.

The user describes their ideal weather with a CityPreferences object (temperature
range, max humidity, clean air, sky, daylight, continents). match_cities() scores
each city's latest observation from 0 to 100 and explains the score in plain words,
e.g. "Lisbon, PT — 92 % match: 22 °C, clean air, 10.4 h daylight, clear sky".

How the score works (each part is 0-1, then a weighted average x 100):
- temperature (weight 40): 1 at the middle of the range, falling to 0.85 at its edges,
                           then minus 0.1 per °C outside it
- humidity    (weight 15): 1 up to the maximum, minus 1/30 per % above it
- air quality (weight 20): 1 up to the maximum AQI, minus 0.35 per AQI step above it
- sky         (weight 15): "clear" → Clear 1, Clouds 0.6, anything else 0.2;
                           "dry"   → no rain/snow/storm 1, otherwise 0
- daylight    (weight 10): 1 from the minimum up, minus 1/3 per hour short of it
A part the user doesn't care about ("any sky", "any air") is left out of the average,
and a part with no data for that city (e.g. no air-quality reading) counts as 0.5.
Pure pandas, so it can be tested with small hand-made tables.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .analytics import AQI_LABELS, latest_by_location
from .exceptions import InvalidInputError

SKY_OPTIONS = {"any": "Don't mind", "clear": "Sunny / clear", "dry": "No rain or snow"}
WET_CONDITIONS = {"Rain", "Drizzle", "Thunderstorm", "Snow"}
WEIGHTS = {"temperature": 40, "humidity": 15, "air": 20, "sky": 15, "daylight": 10}


@dataclass(frozen=True)
class CityPreferences:
    """What the user is looking for. Validated on creation, so bad input fails early."""

    min_temp: float = 18.0
    max_temp: float = 26.0
    max_humidity: float = 70.0
    max_aqi: int | None = 2              # 1 Good ... 5 Very poor; None = don't care
    sky: str = "any"                     # a key of SKY_OPTIONS
    min_daylight: float = 0.0            # hours
    continents: tuple = ()               # empty = everywhere

    def __post_init__(self):
        if self.min_temp > self.max_temp:
            raise InvalidInputError("The minimum temperature can't be above the maximum.")
        if not 0 <= self.max_humidity <= 100:
            raise InvalidInputError("Maximum humidity must be between 0 and 100 %.")
        if self.max_aqi is not None and self.max_aqi not in AQI_LABELS:
            raise InvalidInputError("Maximum air-quality index must be 1-5 (or None).")
        if self.sky not in SKY_OPTIONS:
            raise InvalidInputError(f"Sky must be one of {', '.join(SKY_OPTIONS)}.")
        if not 0 <= self.min_daylight <= 24:
            raise InvalidInputError("Minimum daylight must be between 0 and 24 hours.")
        object.__setattr__(self, "continents", tuple(self.continents))

    def __str__(self):
        parts = [f"{self.min_temp:g} to {self.max_temp:g} °C", f"humidity ≤ {self.max_humidity:g} %"]
        if self.max_aqi is not None:
            parts.append(f"air {AQI_LABELS[self.max_aqi].lower()} or better")
        if self.sky != "any":
            parts.append(SKY_OPTIONS[self.sky].lower())
        if self.min_daylight:
            parts.append(f"≥ {self.min_daylight:g} h daylight")
        if self.continents:
            parts.append("in " + ", ".join(self.continents))
        return " · ".join(parts)


# Ready-made profiles for the people the app is built for.
PRESETS = {
    "Pleasant & clean air": CityPreferences(),
    "Remote work base": CityPreferences(17, 25, 70, 2, "dry", 10),
    "Beach break": CityPreferences(25, 33, 85, None, "clear", 11),
    "City sightseeing": CityPreferences(12, 22, 75, 3, "dry", 0),
    "Winter / snow trip": CityPreferences(-15, 0, 100, None, "any", 0),
}


def _distance_score(value, low, high, per_unit):
    """1 inside [low, high], then minus `per_unit` per unit outside, never below 0."""
    gap = np.maximum(low - value, 0) + np.maximum(value - high, 0)
    return np.clip(1 - per_unit * gap, 0, 1)


def _component_scores(latest, prefs):
    """One column per scored part (0-1). Parts the user doesn't care about are skipped."""
    temp = pd.to_numeric(latest["temperature"], errors="coerce")
    humidity = pd.to_numeric(latest["humidity"], errors="coerce")
    aqi = pd.to_numeric(latest["aqi"], errors="coerce")
    daylight = pd.to_numeric(latest["daylight_hours"], errors="coerce")
    sky = latest["weather_main"]

    parts = pd.DataFrame(index=latest.index)
    centre = (prefs.min_temp + prefs.max_temp) / 2
    half_width = max((prefs.max_temp - prefs.min_temp) / 2, 0.5)
    inside = 1 - 0.15 * np.minimum(np.abs(temp - centre) / half_width, 1)
    parts["temperature"] = np.where(temp.between(prefs.min_temp, prefs.max_temp), inside,
                                    0.85 * _distance_score(temp, prefs.min_temp, prefs.max_temp, 0.1))
    parts["humidity"] = _distance_score(humidity, 0, prefs.max_humidity, 1 / 30)
    if prefs.max_aqi is not None:
        parts["air"] = _distance_score(aqi, 1, prefs.max_aqi, 0.35)
    if prefs.sky == "clear":
        parts["sky"] = sky.map(lambda s: 1.0 if s == "Clear" else 0.6 if s == "Clouds" else 0.2)
        parts.loc[sky.isna(), "sky"] = np.nan
    elif prefs.sky == "dry":
        parts["sky"] = sky.map(lambda s: 0.0 if s in WET_CONDITIONS else 1.0)
        parts.loc[sky.isna(), "sky"] = np.nan
    if prefs.min_daylight:
        parts["daylight"] = _distance_score(daylight, prefs.min_daylight, 24, 1 / 3)
    return parts.astype(float).fillna(0.5)          # no data for that part -> neutral


def _reason(row):
    """'22 °C, clean air, 10.4 h daylight, clear sky' — the facts behind a match."""
    bits = [f"{row['temperature']:.0f} °C", f"{row['humidity']:.0f} % humidity"]
    if pd.notna(row.get("aqi_label")):
        bits.append("clean air" if float(row["aqi"]) <= 2 else f"{row['aqi_label'].lower()} air")
    if pd.notna(row.get("daylight_hours")):
        bits.append(f"{row['daylight_hours']:.1f} h daylight")
    if pd.notna(row.get("description")):
        bits.append(str(row["description"]))
    return ", ".join(bits)


def match_cities(df, prefs):
    """Every city's latest observation scored against `prefs`, best match first.

    Adds 'match_score' (0-100), one '<part>_fit' column per scored part, 'reason'
    (plain-words summary) and 'match_rank'. Cities outside the chosen continents
    are left out.
    """
    latest = latest_by_location(df)
    if prefs.continents and not latest.empty:
        latest = latest[latest["continent"].isin(prefs.continents)]
    if latest.empty:
        return latest.assign(match_score=pd.Series(dtype=float), reason=pd.Series(dtype=object),
                             match_rank=pd.Series(dtype=int))
    latest = latest.reset_index(drop=True)
    parts = _component_scores(latest, prefs)
    weights = pd.Series({p: WEIGHTS[p] for p in parts.columns})
    out = latest.copy()
    out["match_score"] = (100 * (parts * weights).sum(axis=1) / weights.sum()).round(0)
    for part in parts.columns:
        out[f"{part}_fit"] = (100 * parts[part]).round(0)
    out["reason"] = out.apply(_reason, axis=1)
    out = out.sort_values(["match_score", "comfort_index"], ascending=False).reset_index(drop=True)
    out.insert(0, "match_rank", range(1, len(out) + 1))
    return out


def match_sentence(row):
    """'Lisbon, PT — 92 % match: 22 °C, 55 % humidity, clean air, ...'"""
    return f"{row['location']} — {row['match_score']:.0f} % match: {row['reason']}"
