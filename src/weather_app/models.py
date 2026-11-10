"""Data classes: one WeatherSnapshot = one city's conditions at one moment."""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from .exceptions import APIServiceError

IDEAL_TEMPERATURE_C = 21


def comfort_index(temperature, humidity, wind_speed):
    """Our own 0-100 'how pleasant is it outside' score (100 = perfect).

    Start from 100 and subtract penalties:
    - 3 points per °C away from 21 °C
    - 0.5 points per % humidity outside the comfortable 40-60 % band
    - 4 points per m/s of wind above a light breeze (3 m/s)

    Written with numpy so the SAME function works on single numbers (inside a
    WeatherSnapshot) and on whole pandas columns (inside analytics.py).
    """
    temp_penalty = 3 * np.abs(np.asarray(temperature, dtype=float) - IDEAL_TEMPERATURE_C)
    humidity_penalty = 0.5 * np.maximum(0, np.abs(np.asarray(humidity, dtype=float) - 50) - 10)
    wind_penalty = 4 * np.maximum(0, np.asarray(wind_speed, dtype=float) - 3)
    score = np.clip(100 - temp_penalty - humidity_penalty - wind_penalty, 0, 100)
    return float(score) if np.ndim(score) == 0 else score


def comfort_label(score):
    """Turn a comfort score into words a user understands."""
    if score >= 80:
        return "Very comfortable"
    if score >= 60:
        return "Comfortable"
    if score >= 40:
        return "Mixed"
    if score >= 20:
        return "Uncomfortable"
    return "Harsh"


def _ts(value):
    """Unix timestamp from the API -> timezone-aware UTC datetime (None stays None)."""
    return datetime.fromtimestamp(value, tz=timezone.utc) if value is not None else None


class AirQuality:
    """Air pollution for one place, from OpenWeatherMap's free Air Pollution API.

    aqi is the API's index from 1 (Good) to 5 (Very poor); the components are
    concentrations in µg/m³.
    """

    LABELS = {1: "Good", 2: "Fair", 3: "Moderate", 4: "Poor", 5: "Very poor"}
    COMPONENTS = ["co", "no2", "o3", "so2", "pm2_5", "pm10"]

    def __init__(self, aqi, co=None, no2=None, o3=None, so2=None, pm2_5=None, pm10=None):
        if aqi not in self.LABELS:
            raise ValueError(f"AQI must be 1-5, got {aqi!r}")
        self.aqi = aqi
        self.co, self.no2, self.o3, self.so2 = co, no2, o3, so2
        self.pm2_5, self.pm10 = pm2_5, pm10

    @classmethod
    def from_api(cls, data):
        try:
            item = data["list"][0]
            components = item.get("components", {})
            return cls(item["main"]["aqi"], **{k: components.get(k) for k in cls.COMPONENTS})
        except (KeyError, TypeError, IndexError, ValueError) as e:
            raise APIServiceError(f"The air-quality response was missing a field: {e}") from e

    @property
    def label(self):
        """1 -> 'Good' ... 5 -> 'Very poor'."""
        return self.LABELS[self.aqi]

    def to_dict(self):
        return {"aqi": self.aqi, **{k: getattr(self, k) for k in self.COMPONENTS}}

    def __repr__(self):
        return f"AirQuality(aqi={self.aqi}, pm2_5={self.pm2_5})"

    def __str__(self):
        return f"{self.label} (AQI {self.aqi}, PM2.5 {self.pm2_5} µg/m³)"

    def __lt__(self, other):
        """Cleaner air sorts first: sorted() goes from Good to Very poor."""
        if not isinstance(other, AirQuality):
            return NotImplemented
        return (self.aqi, self.pm2_5 or 0) < (other.aqi, other.pm2_5 or 0)


class WeatherSnapshot:
    """Current conditions for one city, as returned by one API call."""

    # Order of the columns in the CSV log (storage.py uses this).
    # New columns are only ever ADDED AT THE END, so older log files can be upgraded
    # by adding empty columns (see WeatherLog._upgrade_columns).
    FIELDS = [
        "fetched_at", "observed_at", "query", "city", "country", "lat", "lon",
        "temperature", "feels_like", "temp_min", "temp_max", "humidity",
        "pressure", "wind_speed", "clouds", "description",
        # added 31 Oct 2026: more of what the weather API already returns
        "weather_main", "wind_deg", "wind_gust", "visibility", "rain_1h", "snow_1h",
        "sunrise", "sunset", "timezone_offset", "sea_level", "grnd_level",
        # added 31 Oct 2026: air quality (second request per city)
        "aqi", *AirQuality.COMPONENTS,
    ]

    def __init__(self, city, country, temperature, feels_like, humidity, wind_speed,
                 description="", temp_min=None, temp_max=None, pressure=None,
                 clouds=None, lat=None, lon=None, observed_at=None, fetched_at=None,
                 query=None, weather_main=None, wind_deg=None, wind_gust=None,
                 visibility=None, rain_1h=None, snow_1h=None, sunrise=None, sunset=None,
                 timezone_offset=None, sea_level=None, grnd_level=None, air_quality=None):
        self.city = city
        self.country = country
        self.query = query or city
        self.lat = lat
        self.lon = lon
        self.temperature = float(temperature)
        self.feels_like = float(feels_like)
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.humidity = float(humidity)
        self.pressure = pressure
        self.wind_speed = float(wind_speed)
        self.clouds = clouds
        self.description = description
        now = datetime.now(timezone.utc)
        self.observed_at = observed_at or now   # when OpenWeatherMap measured it
        self.fetched_at = fetched_at or now     # when OUR app asked for it
        self.weather_main = weather_main        # "Clear", "Clouds", "Rain", "Snow"...
        self.wind_deg = wind_deg                # direction the wind comes from, degrees
        self.wind_gust = wind_gust              # m/s
        self.visibility = visibility            # metres, capped at 10,000
        self.rain_1h = rain_1h                  # mm in the last hour
        self.snow_1h = snow_1h
        self.sunrise = sunrise                  # UTC datetimes
        self.sunset = sunset
        self.timezone_offset = timezone_offset  # seconds from UTC
        self.sea_level = sea_level              # hPa
        self.grnd_level = grnd_level            # hPa at ground height
        self.air_quality = air_quality          # AirQuality or None (fetched separately)

    # ---------- building objects ----------

    @classmethod
    def from_api(cls, data, query=None):
        """Parse OpenWeatherMap's nested JSON into a flat snapshot (s13 _parse_data idea)."""
        try:
            return cls(
                city=data["name"],
                country=data.get("sys", {}).get("country", ""),
                lat=data.get("coord", {}).get("lat"),
                lon=data.get("coord", {}).get("lon"),
                temperature=data["main"]["temp"],
                feels_like=data["main"]["feels_like"],
                temp_min=data["main"].get("temp_min"),
                temp_max=data["main"].get("temp_max"),
                humidity=data["main"]["humidity"],
                pressure=data["main"].get("pressure"),
                wind_speed=data.get("wind", {}).get("speed", 0.0),
                clouds=data.get("clouds", {}).get("all"),
                description=data["weather"][0]["description"] if data.get("weather") else "",
                observed_at=datetime.fromtimestamp(data["dt"], tz=timezone.utc) if "dt" in data else None,
                query=query,
                weather_main=data["weather"][0].get("main") if data.get("weather") else None,
                wind_deg=data.get("wind", {}).get("deg"),
                wind_gust=data.get("wind", {}).get("gust"),
                visibility=data.get("visibility"),
                # The API leaves "rain"/"snow" out entirely when there is none -> 0 mm.
                rain_1h=data.get("rain", {}).get("1h", 0.0),
                snow_1h=data.get("snow", {}).get("1h", 0.0),
                sunrise=_ts(data.get("sys", {}).get("sunrise")),
                sunset=_ts(data.get("sys", {}).get("sunset")),
                timezone_offset=data.get("timezone"),
                sea_level=data["main"].get("sea_level"),
                grnd_level=data["main"].get("grnd_level"),
            )
        except (KeyError, TypeError, IndexError) as e:
            raise APIServiceError(f"The API response was missing a field: {e}") from e

    def to_dict(self):
        """Flat dict in FIELDS order — one row of the CSV log."""
        return {
            "fetched_at": self.fetched_at.isoformat(),
            "observed_at": self.observed_at.isoformat(),
            "query": self.query,
            "city": self.city,
            "country": self.country,
            "lat": self.lat,
            "lon": self.lon,
            "temperature": self.temperature,
            "feels_like": self.feels_like,
            "temp_min": self.temp_min,
            "temp_max": self.temp_max,
            "humidity": self.humidity,
            "pressure": self.pressure,
            "wind_speed": self.wind_speed,
            "clouds": self.clouds,
            "description": self.description,
            "weather_main": self.weather_main,
            "wind_deg": self.wind_deg,
            "wind_gust": self.wind_gust,
            "visibility": self.visibility,
            "rain_1h": self.rain_1h,
            "snow_1h": self.snow_1h,
            "sunrise": self.sunrise.isoformat() if self.sunrise else None,
            "sunset": self.sunset.isoformat() if self.sunset else None,
            "timezone_offset": self.timezone_offset,
            "sea_level": self.sea_level,
            "grnd_level": self.grnd_level,
            # one column per air-quality value; empty if it wasn't fetched
            **(self.air_quality.to_dict() if self.air_quality
               else dict.fromkeys(["aqi", *AirQuality.COMPONENTS])),
        }

    # ---------- derived values (@property) ----------

    @property
    def label(self):
        """'Madrid, ES' — handy for displays and charts."""
        return f"{self.city}, {self.country}" if self.country else self.city

    @property
    def daylight_hours(self):
        """Hours between sunrise and sunset (None if unknown)."""
        if self.sunrise is None or self.sunset is None:
            return None
        return round((self.sunset - self.sunrise).total_seconds() / 3600, 1)

    @property
    def local_time(self):
        """When the observation was made, in the CITY's own local time."""
        if self.timezone_offset is None:
            return None
        return self.observed_at + timedelta(seconds=self.timezone_offset)

    @property
    def is_daytime(self):
        """True between sunrise and sunset."""
        if self.sunrise is None or self.sunset is None:
            return None
        return self.sunrise <= self.observed_at <= self.sunset

    @property
    def comfort_index(self):
        """0-100 comfort score computed from temperature, humidity and wind."""
        return round(comfort_index(self.temperature, self.humidity, self.wind_speed), 1)

    @property
    def comfort_label(self):
        return comfort_label(self.comfort_index)

    @property
    def feels_like_delta(self):
        """Feels-like minus actual: negative = feels colder than the thermometer says."""
        return round(self.feels_like - self.temperature, 1)

    @property
    def wind_kmh(self):
        """The API gives m/s (metric units); most people think in km/h."""
        return round(self.wind_speed * 3.6, 1)

    # ---------- special methods ----------

    def __repr__(self):
        return (f"WeatherSnapshot({self.city!r}, {self.country!r}, "
                f"{self.temperature}°C, observed_at={self.observed_at:%Y-%m-%d %H:%M}Z)")

    def __str__(self):
        return (f"{self.label}: {self.temperature:.1f}°C (feels {self.feels_like:.1f}°C), "
                f"{self.description}, humidity {self.humidity:.0f}%, "
                f"wind {self.wind_kmh} km/h — comfort {self.comfort_index}/100")

    def __eq__(self, other):
        """Same city measured at the same moment = the same observation.

        Lets us spot duplicates: OpenWeatherMap only refreshes every ~10 minutes,
        so two quick fetches can return the identical observation.
        """
        if not isinstance(other, WeatherSnapshot):
            return NotImplemented
        return (self.city, self.country, self.observed_at) == (
            other.city, other.country, other.observed_at)

    def __hash__(self):
        # Needed because we defined __eq__; lets snapshots go in a set().
        return hash((self.city, self.country, self.observed_at))

    def __lt__(self, other):
        """Order by temperature, so sorted(snapshots) goes coldest -> warmest."""
        if not isinstance(other, WeatherSnapshot):
            return NotImplemented
        return self.temperature < other.temperature


class ForecastPoint(WeatherSnapshot):
    """One 3-hour step of the 5-day forecast.

    Inherits from WeatherSnapshot because a forecast step has exactly the same
    fields (temperature, humidity, wind...) and therefore gets comfort_index,
    wind_kmh, feels_like_delta, sorting by temperature, etc. for free.
    It only adds what a forecast has and an observation doesn't: the chance of
    rain and the expected rain amount.

    Here `observed_at` means "the time this prediction is FOR", not a measurement.
    """

    def __init__(self, *args, rain_probability=0.0, rain_mm=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.rain_probability = float(rain_probability)   # 0.0 - 1.0
        self.rain_mm = float(rain_mm)                       # mm over the 3 hours

    @classmethod
    def from_forecast_item(cls, item, city, country="", lat=None, lon=None):
        """Parse one element of the forecast API's "list" array."""
        try:
            return cls(
                city=city,
                country=country,
                lat=lat,
                lon=lon,
                temperature=item["main"]["temp"],
                feels_like=item["main"]["feels_like"],
                temp_min=item["main"].get("temp_min"),
                temp_max=item["main"].get("temp_max"),
                humidity=item["main"]["humidity"],
                pressure=item["main"].get("pressure"),
                wind_speed=item.get("wind", {}).get("speed", 0.0),
                clouds=item.get("clouds", {}).get("all"),
                description=item["weather"][0]["description"] if item.get("weather") else "",
                observed_at=datetime.fromtimestamp(item["dt"], tz=timezone.utc),
                rain_probability=item.get("pop", 0.0),
                rain_mm=item.get("rain", {}).get("3h", 0.0),
            )
        except (KeyError, TypeError, IndexError) as e:
            raise APIServiceError(f"The forecast response was missing a field: {e}") from e

    @property
    def rain_chance_pct(self):
        """Chance of rain as a percentage, e.g. 40 instead of 0.4."""
        return round(self.rain_probability * 100)

    def __repr__(self):
        return (f"ForecastPoint({self.city!r}, {self.temperature}°C, "
                f"for={self.observed_at:%Y-%m-%d %H:%M}Z, rain={self.rain_chance_pct}%)")

    def to_dict(self):
        row = super().to_dict()
        row["rain_probability"] = self.rain_probability
        row["rain_mm"] = self.rain_mm
        return row


class Forecast:
    """The whole 5-day forecast for one city: a sequence of ForecastPoints."""

    def __init__(self, city, country, points):
        self.city = city
        self.country = country
        self.points = sorted(points, key=lambda p: p.observed_at)

    @classmethod
    def from_api(cls, data):
        try:
            info = data["city"]
            city, country = info["name"], info.get("country", "")
            lat, lon = info.get("coord", {}).get("lat"), info.get("coord", {}).get("lon")
            points = [ForecastPoint.from_forecast_item(item, city, country, lat, lon)
                      for item in data["list"]]
        except (KeyError, TypeError) as e:
            raise APIServiceError(f"The forecast response was missing a field: {e}") from e
        return cls(city, country, points)

    @property
    def label(self):
        return f"{self.city}, {self.country}" if self.country else self.city

    @property
    def warmest(self):
        """Warmest step — max() works because ForecastPoint inherits __lt__."""
        return max(self.points) if self.points else None

    @property
    def coldest(self):
        return min(self.points) if self.points else None

    def to_dataframe(self):
        """One row per 3-hour step, with the derived metrics already added."""
        return pd.DataFrame([{
            "time": p.observed_at,
            "temperature": p.temperature,
            "feels_like": p.feels_like,
            "humidity": p.humidity,
            "wind_kmh": p.wind_kmh,
            "rain_chance": p.rain_chance_pct,
            "rain_mm": p.rain_mm,
            "comfort_index": p.comfort_index,
            "description": p.description,
        } for p in self.points])

    def __len__(self):
        return len(self.points)

    def __iter__(self):
        """Lets you write `for point in forecast:`."""
        return iter(self.points)

    def __repr__(self):
        return f"Forecast({self.label!r}, {len(self)} points)"
