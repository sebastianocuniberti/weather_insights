"""Shared test fixtures: a realistic fake API response (no network needed)."""

import sys
from pathlib import Path

import pytest

# Import weather_app straight from src/, so the tests always run the current code even when
# the editable install is skipped (macOS/iCloud can hide the .pth file, which Python 3.13 ignores).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture
def madrid_json():
    """Shape copied from a real OpenWeatherMap /weather response."""
    return {
        "coord": {"lon": -3.7026, "lat": 40.4165},
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
        "main": {"temp": 22.0, "feels_like": 21.5, "temp_min": 20.0, "temp_max": 24.0,
                 "pressure": 1018, "humidity": 40},
        "wind": {"speed": 2.0, "deg": 200},
        "clouds": {"all": 0},
        "dt": 1793448000,
        "sys": {"country": "ES"},
        "name": "Madrid",
        "cod": 200,
    }
