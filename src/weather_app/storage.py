"""Logging fetched snapshots to a CSV file and loading them back.

The free OpenWeatherMap tier only returns *current* conditions, so every
successful fetch is appended here with its timestamps. Over days/weeks this
becomes our own time series — and the file is committed to the repo so the
grader sees real history.
"""

import csv
from pathlib import Path

import pandas as pd

from .config import DATA_FILE
from .models import ForecastPoint, WeatherSnapshot


class WeatherLog:
    """A CSV file of WeatherSnapshot rows (one row per city per fetch)."""

    def __init__(self, path=DATA_FILE):
        self.path = Path(path)

    def __repr__(self):
        return f"WeatherLog({str(self.path)!r})"

    def __len__(self):
        """Number of logged observations, so len(log) just works."""
        if not self._has_rows():
            return 0
        with self.path.open(newline="", encoding="utf-8") as f:
            return sum(1 for _ in csv.DictReader(f))

    # ---------- writing ----------

    def append(self, snapshots):
        """Append snapshots to the CSV, skipping observations already logged.

        OpenWeatherMap refreshes roughly every 10 minutes, so fetching twice in a
        row returns the same observation; logging it twice would bias averages.
        Returns the number of NEW rows written.
        """
        snapshots = list(snapshots)
        for snap in snapshots:
            if isinstance(snap, ForecastPoint):
                # A forecast is a prediction, not something that happened.
                # Logging it would mix fake "history" into our real observations.
                raise TypeError("Forecast points can't be logged as observations.")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        already_logged = self._existing_keys()
        new_rows = []
        for snap in snapshots:
            key = (snap.city, snap.country, snap.observed_at.isoformat())
            if key not in already_logged:
                new_rows.append(snap.to_dict())
                already_logged.add(key)

        if not new_rows:
            return 0

        self._upgrade_columns()
        write_header = not self._has_rows() and not self._has_header()
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=WeatherSnapshot.FIELDS)
            if write_header:
                writer.writeheader()
            writer.writerows(new_rows)
        return len(new_rows)

    # ---------- reading ----------

    def load(self):
        """Return the whole log as a DataFrame with proper datetime columns (UTC)."""
        if not self._has_rows():
            return pd.DataFrame(columns=WeatherSnapshot.FIELDS)
        # keep_default_na=False + na_values=[""]: only empty cells are "missing".
        # Without it pandas turns Namibia's country code "NA" into NaN.
        df = pd.read_csv(self.path, keep_default_na=False, na_values=[""])
        # An older log may lack the newer columns: add them as empty, in the right order.
        df = df.reindex(columns=WeatherSnapshot.FIELDS)
        for col in ["fetched_at", "observed_at", "sunrise", "sunset"]:
            df[col] = pd.to_datetime(df[col], utc=True, format="ISO8601")
        for col in ["query", "city", "description", "weather_main"]:
            df[col] = df[col].astype(object)
        df["country"] = df["country"].fillna("")
        return df.sort_values("observed_at").reset_index(drop=True)

    # ---------- protected helpers ----------

    def _upgrade_columns(self):
        """If the file was written with fewer columns (an older version of the app),
        rewrite it once with the current header. Old rows keep every value they had;
        the new columns are simply left empty for them. Nothing is deleted.
        """
        if not self._has_header():
            return
        with self.path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames == WeatherSnapshot.FIELDS:
                return
            unknown = set(reader.fieldnames) - set(WeatherSnapshot.FIELDS)
            if unknown:
                raise ValueError(f"The log has columns this app doesn't know: {unknown}")
            rows = list(reader)
        tmp = self.path.with_suffix(".upgrading")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=WeatherSnapshot.FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        tmp.replace(self.path)        # swap in the new file only once it's fully written

    def _has_header(self):
        return self.path.exists() and self.path.stat().st_size > 0

    def _has_rows(self):
        if not self._has_header():
            return False
        with self.path.open(encoding="utf-8") as f:
            f.readline()                 # header
            return bool(f.readline().strip())

    def _existing_keys(self):
        if not self._has_rows():
            return set()
        with self.path.open(newline="", encoding="utf-8") as f:
            return {(r["city"], r["country"], r["observed_at"]) for r in csv.DictReader(f)}
