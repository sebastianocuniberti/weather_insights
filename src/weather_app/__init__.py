"""Weather Insights: OpenWeatherMap client, history log and analytics."""

from .client import APIClient, OpenWeatherClient, validate_city_name
from .exceptions import (
    APIServiceError,
    InvalidAPIKeyError,
    InvalidInputError,
    LocationNotFoundError,
    RateLimitError,
    WeatherAppError,
)
from .models import WeatherSnapshot
from .storage import WeatherLog

__all__ = [
    "APIClient", "OpenWeatherClient", "validate_city_name", "WeatherSnapshot",
    "WeatherLog", "WeatherAppError", "InvalidInputError", "LocationNotFoundError",
    "InvalidAPIKeyError", "RateLimitError", "APIServiceError",
]
