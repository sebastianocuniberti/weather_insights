"""Environment configuration.

The API key lives in `variables.env` at the repo root (never committed) and is
loaded with python-dotenv, the same convention used in s07/s13.

Unlike the starter template we do NOT raise at import time: the Streamlit app
and the tests should still be able to import the package when no key is set,
and show a friendly message instead of crashing.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / "variables.env"
DATA_FILE = PROJECT_ROOT / "data" / "weather_log.csv"

load_dotenv(ENV_FILE)


def get_api_key():
    """Return the OpenWeatherMap API key, or raise a clear error if it is missing."""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "OPENWEATHER_API_KEY is not set. Copy variables.env.example to "
            "variables.env and fill in your own key."
        )
    return api_key
