"""API client classes.

APIClient            -> knows HOW to call any JSON API (request, timeout, status
                        codes, raise on failure). Nothing in it is weather-specific,
                        so another provider (e.g. WeatherAPI.com, a stock API)
                        could subclass it too.
OpenWeatherClient    -> knows WHICH API: the OpenWeatherMap endpoint, its
                        parameters and its JSON fields.
"""

import re
import time
from collections import deque

import requests

from .exceptions import (
    APIServiceError,
    InvalidAPIKeyError,
    InvalidInputError,
    LocationNotFoundError,
    RateLimitError,
    WeatherAppError,
)
from .models import AirQuality, Forecast, WeatherSnapshot

# Must start with a letter (accents included); after that only letters, spaces,
# dots, commas, hyphens and apostrophes. Accepts "Venice", "São Paulo",
# "St. John's", "Paris,FR"; rejects "123", "@@@", "Madrid2".
# ([^\W\d_] means "a word character that is not a digit or underscore" = a letter.)
_CITY_PATTERN = re.compile(r"[^\W\d_](?:[^\W\d_]|[ .,'\-])*")


def validate_city_name(city):
    """Clean a city name and reject obviously invalid input BEFORE calling the API.

    Returns the cleaned name (extra spaces removed) or raises InvalidInputError.
    """
    if not isinstance(city, str):
        raise InvalidInputError("The city name must be text.")

    cleaned = " ".join(city.split())  # strip + collapse repeated spaces
    if not cleaned:
        raise InvalidInputError("Please type a city name — the field is empty.")
    if len(cleaned) < 2:
        raise InvalidInputError(f"'{cleaned}' is too short to be a city name.")
    if len(cleaned) > 85:
        raise InvalidInputError("That name is too long to be a city name.")
    if not _CITY_PATTERN.fullmatch(cleaned):
        raise InvalidInputError(
            f"'{cleaned}' contains characters a city name can't have "
            "(numbers or symbols). Use e.g. 'Madrid' or 'Paris,FR'."
        )
    return cleaned


class APIClient:
    """Generic JSON API client: builds the request, checks the status, raises on failure.

    Encapsulation choices:
    - base_url, timeout        public: callers may read them.
    - _auth_param_name         protected: subclasses set the name of the query
                               parameter their provider expects for the key.
    - _get, _handle_error      protected: helpers subclasses use/extend.
    - __api_key                private (name-mangled): the secret must only ever be
                               used inside this class. Subclasses never touch it
                               directly, and it is hidden from __repr__, so it can't
                               leak into the Streamlit UI or a log by accident.
    - __call_times             private: timestamps of recent requests, used by the
                               rate limiter. Nobody outside should edit them.

    Rate limiting: most APIs cap requests per minute, so the base class can
    enforce a cap for ANY provider. Pass max_calls_per_minute=None for no limit.
    """

    _auth_param_name = "api_key"

    def __init__(self, base_url, api_key, timeout=10, max_calls_per_minute=None):
        if not api_key:
            raise InvalidAPIKeyError("No API key was provided.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_calls_per_minute = max_calls_per_minute
        self.__api_key = api_key
        self.__call_times = deque()
        self._session = requests.Session()
        # The clock and sleep function are attributes so tests can swap in fake
        # ones and check the limiter without really waiting a minute.
        self._clock = time.monotonic
        self._sleep = time.sleep
        self.on_wait = None          # optional callback(seconds) while pausing

    def _wait_for_rate_limit(self):
        """Pause if the last `max_calls_per_minute` requests all happened < 60 s ago."""
        if not self.max_calls_per_minute:
            return
        now = self._clock()
        while self.__call_times and now - self.__call_times[0] >= 60:
            self.__call_times.popleft()               # forget requests older than 1 min
        if len(self.__call_times) >= self.max_calls_per_minute:
            wait = 60 - (now - self.__call_times[0]) + 0.5
            if self.on_wait is not None:
                self.on_wait(wait)
            self._sleep(wait)
            self.__call_times.popleft()
        self.__call_times.append(self._clock())

    def __repr__(self):
        return f"{type(self).__name__}(base_url={self.base_url!r}, api_key='***')"

    def _get(self, endpoint, params=None):
        """GET `endpoint` and return the decoded JSON, or raise a specific error."""
        query = dict(params or {})
        query[self._auth_param_name] = self.__api_key
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        self._wait_for_rate_limit()

        try:
            response = self._session.get(url, params=query, timeout=self.timeout)
        except requests.exceptions.Timeout as e:
            raise APIServiceError(
                f"The server took longer than {self.timeout}s to answer. Try again."
            ) from e
        except requests.exceptions.ConnectionError as e:
            raise APIServiceError(
                "Could not reach the server — check your internet connection."
            ) from e
        except requests.exceptions.RequestException as e:
            raise APIServiceError(f"The request failed: {type(e).__name__}") from e

        if response.status_code != 200:
            self._handle_error(response)

        try:
            return response.json()
        except ValueError as e:
            raise APIServiceError("The server sent a response that isn't valid JSON.") from e

    def _handle_error(self, response):
        """Translate an HTTP error status into one of our exception classes.

        Subclasses can override this to add provider-specific messages.
        """
        code = response.status_code
        if code == 401:
            raise InvalidAPIKeyError(
                "The API key was rejected (invalid, expired, or not activated yet — "
                "new OpenWeatherMap keys can take up to 2 hours)."
            )
        if code == 404:
            raise LocationNotFoundError("The requested resource was not found.")
        if code == 429:
            raise RateLimitError("Too many requests — wait a minute and try again.")
        if 500 <= code < 600:
            raise APIServiceError(f"The weather service is having problems (status {code}).")
        raise APIServiceError(f"Unexpected response from the server (status {code}).")


class OpenWeatherClient(APIClient):
    """Client for OpenWeatherMap's free 'current weather' endpoint."""

    BASE_URL = "https://api.openweathermap.org/data/2.5"
    _auth_param_name = "appid"

    # The free plan allows 60 requests per minute; 55 leaves a safety margin.
    FREE_PLAN_CALLS_PER_MINUTE = 55

    def __init__(self, api_key, units="metric", timeout=10,
                 max_calls_per_minute=FREE_PLAN_CALLS_PER_MINUTE):
        super().__init__(self.BASE_URL, api_key, timeout=timeout,
                         max_calls_per_minute=max_calls_per_minute)
        self.units = units

    def _handle_error(self, response):
        # OpenWeatherMap uses 404 for "city not found", so give a clearer message.
        if response.status_code == 404:
            raise LocationNotFoundError(
                "OpenWeatherMap doesn't know that city. Check the spelling, or add a "
                "country code like 'Valencia,ES'."
            )
        super()._handle_error(response)

    def current(self, city):
        """Fetch current conditions for one city and return a WeatherSnapshot."""
        cleaned = validate_city_name(city)
        data = self._get("weather", {"q": cleaned, "units": self.units})
        return WeatherSnapshot.from_api(data, query=cleaned)

    def forecast(self, city):
        """5-day forecast in 3-hour steps (free tier) for one city -> Forecast.

        Reuses _get() from the base class, so it gets the same validation, timeout
        and error handling as current() without writing any of it again.
        """
        cleaned = validate_city_name(city)
        data = self._get("forecast", {"q": cleaned, "units": self.units})
        return Forecast.from_api(data)

    def air_quality(self, lat, lon):
        """Current air pollution at a coordinate (free Air Pollution API) -> AirQuality.

        This endpoint works with coordinates, not names, so we call it right after
        current(), which tells us the city's lat/lon.
        """
        if lat is None or lon is None:
            raise InvalidInputError("Air quality needs a latitude and longitude.")
        data = self._get("air_pollution", {"lat": lat, "lon": lon})
        return AirQuality.from_api(data)

    def fetch_many(self, cities, on_progress=None, with_air_quality=False):
        """Fetch several cities; one bad city never stops the others (s13 batch pattern).

        Returns (snapshots, errors) where errors maps city -> human-readable message.
        Exception: a rejected API key fails for every city in exactly the same way,
        so we stop early instead of repeating the same error N times.

        on_progress: optional function called as on_progress(done, total, city) before
        each request — the app uses it to move a progress bar during long fetches.

        with_air_quality: also fetch air pollution for each city (one extra request
        per city). If only the air-quality request fails, the weather is still kept
        and the problem is reported as "<city> (air quality)" in errors.
        """
        snapshots = []
        errors = {}
        for i, city in enumerate(cities):
            if on_progress is not None:
                on_progress(i, len(cities), city)
            try:
                snapshot = self.current(city)
                snapshots.append(snapshot)
                if with_air_quality:
                    try:
                        snapshot.air_quality = self.air_quality(snapshot.lat, snapshot.lon)
                    except InvalidAPIKeyError:
                        raise
                    except WeatherAppError as e:
                        errors[f"{city} (air quality)"] = str(e)
            except InvalidAPIKeyError as e:
                errors[city] = str(e)
                for other in cities[i + 1:]:
                    errors[other] = "Skipped: the API key was rejected."
                break
            except WeatherAppError as e:
                # bad input, unknown city, rate limit, timeout/5xx for this one city
                errors[city] = str(e)
        return snapshots, errors
