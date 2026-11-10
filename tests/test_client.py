"""Client tests with a fake requests session — no network, no real API key."""

import pytest
import requests

from weather_app.client import APIClient, OpenWeatherClient, validate_city_name
from weather_app.exceptions import (
    APIServiceError,
    InvalidAPIKeyError,
    InvalidInputError,
    LocationNotFoundError,
    RateLimitError,
)


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeSession:
    """Returns a prepared response per city name (or raises a prepared exception)."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        result = self.responses[params["q"]]
        if isinstance(result, Exception):
            raise result
        return result


def client_with(responses):
    client = OpenWeatherClient("test-key")
    client._session = FakeSession(responses)
    return client


# ---------- input validation ----------

@pytest.mark.parametrize("good", ["Madrid", "  São   Paulo ", "St. John's", "Paris,FR", "Aix-en-Provence"])
def test_valid_city_names(good):
    assert validate_city_name(good)


@pytest.mark.parametrize("bad", ["", "   ", "x", "12345", "Madrid2", "@@@", None])
def test_invalid_city_names(bad):
    with pytest.raises(InvalidInputError):
        validate_city_name(bad)


def test_invalid_input_never_calls_api():
    client = client_with({})
    with pytest.raises(InvalidInputError):
        client.current("123")
    assert client._session.calls == []


# ---------- one error class per failure mode ----------

def test_success(madrid_json):
    snap = client_with({"Madrid": FakeResponse(200, madrid_json)}).current("Madrid")
    assert snap.city == "Madrid"


@pytest.mark.parametrize("status, error", [
    (404, LocationNotFoundError),
    (401, InvalidAPIKeyError),
    (429, RateLimitError),
    (500, APIServiceError),
    (418, APIServiceError),
])
def test_status_codes_map_to_specific_errors(status, error):
    with pytest.raises(error):
        client_with({"Nowhere": FakeResponse(status)}).current("Nowhere")


def test_network_failures():
    with pytest.raises(APIServiceError, match="internet"):
        client_with({"Madrid": requests.exceptions.ConnectionError()}).current("Madrid")
    with pytest.raises(APIServiceError, match="longer than"):
        client_with({"Madrid": requests.exceptions.Timeout()}).current("Madrid")


# ---------- batch fetch degrades gracefully ----------

def test_fetch_many_skips_bad_cities(madrid_json):
    client = client_with({
        "Madrid": FakeResponse(200, madrid_json),
        "Atlantis": FakeResponse(404),
        "Venice": requests.exceptions.Timeout(),
    })
    snaps, errors = client.fetch_many(["Madrid", "Atlantis", "Venice", "12"])
    assert [s.city for s in snaps] == ["Madrid"]
    assert set(errors) == {"Atlantis", "Venice", "12"}


def test_fetch_many_stops_on_bad_key(madrid_json):
    client = client_with({"Madrid": FakeResponse(401), "Venice": FakeResponse(200, madrid_json)})
    snaps, errors = client.fetch_many(["Madrid", "Venice"])
    assert snaps == []
    assert "Skipped" in errors["Venice"]
    assert len(client._session.calls) == 1   # didn't waste a second call


# ---------- encapsulation ----------

def test_api_key_is_private_and_hidden():
    client = OpenWeatherClient("super-secret")
    assert "super-secret" not in repr(client)
    assert not hasattr(client, "__api_key")
    assert not hasattr(client, "api_key")
    assert client._APIClient__api_key == "super-secret"   # name-mangled


def test_subclass_sends_key_under_its_own_param_name(madrid_json):
    client = client_with({"Madrid": FakeResponse(200, madrid_json)})
    client.current("Madrid")
    assert client._session.calls[0]["appid"] == "test-key"


def test_base_client_requires_key():
    with pytest.raises(InvalidAPIKeyError):
        APIClient("https://example.com", "")
