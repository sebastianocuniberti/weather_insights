"""One exception class per failure mode (s11_error_handling).

Having a separate class for each problem lets the caller react differently to
"you typed the city wrong" vs "your key is broken" vs "the internet is down",
instead of catching one generic error and printing a traceback.
"""


class WeatherAppError(Exception):
    """Base class for every error this package raises on purpose."""


class InvalidInputError(WeatherAppError, ValueError):
    """The user input is obviously invalid, so we don't even call the API."""


class LocationNotFoundError(WeatherAppError):
    """The API answered 404: the location does not exist."""


class InvalidAPIKeyError(WeatherAppError):
    """The API answered 401: the key is wrong, expired, or not yet active."""


class RateLimitError(WeatherAppError):
    """The API answered 429: too many requests in a short time."""


class APIServiceError(WeatherAppError):
    """Network failure, timeout, or a 5xx / unexpected response from the server."""
