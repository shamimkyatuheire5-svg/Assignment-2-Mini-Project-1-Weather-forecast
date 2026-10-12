from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
METNO_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

# WMO weather interpretation codes used by Open-Meteo.
# Source: https://open-meteo.com/en/docs
WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm: Slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class WeatherAPIError(Exception):
    """Raised when a weather API request fails permanently."""


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

def request_json(
    url: str,
    params: dict[str, Any],
    *,
    timeout: float = 10.0,
    retries: int = 3,
    backoff: float = 1.0,
    user_agent: str,
) -> dict[str, Any]:
    """GET *url* with *params* and return the parsed JSON.

    Retries on connection errors, timeouts and 5xx responses with
    exponential backoff. Raises WeatherAPIError on final failure.

    Parameters
    ----------
    url : str
        Endpoint URL.
    params : dict
        Query parameters.
    timeout : float
        Per-request timeout in seconds.
    retries : int
        Maximum number of retries (so total attempts = retries + 1).
    backoff : float
        Base seconds for exponential backoff (backoff * 2**attempt).
    user_agent : str
        Value sent in the User-Agent header. Must contain a real contact.
    """
    headers = {"User-Agent": user_agent}
    last_exc: Exception | None = None
    r: requests.Response | None = None

    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            # Retry on 5xx, fail fast on other 4xx.
            if r.status_code >= 500:
                r.raise_for_status()
            r.raise_for_status()
            return r.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        except requests.HTTPError as exc:
            if r is not None and r.status_code >= 500:
                last_exc = exc
            else:
                body = r.text[:200] if r is not None else ""
                code = r.status_code if r is not None else "?"
                raise WeatherAPIError(f"HTTP {code}: {body}") from exc

        if attempt < retries:
            time.sleep(backoff * (2 ** attempt))

    raise WeatherAPIError(
        f"Request failed after {retries + 1} attempts: {last_exc}"
    ) from last_exc


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------

def geocode(name: str, *, count: int = 5, user_agent: str) -> list[dict[str, Any]]:
    """Return candidate locations for *name*.

    Returns an empty list when the API reports no matches, so the caller
    can decide how to react (e.g. raise, prompt, or fall back).

    Parameters
    ----------
    name : str
        City name, e.g. "Dresden".
    count : int
        Maximum number of candidates to request (1–100).
    user_agent : str
        Contact string sent in the User-Agent header.
    """
    if not name or not name.strip():
        raise ValueError("City name must not be empty")

    payload = request_json(
        GEOCODING_URL,
        {
            "name": name.strip(),
            "count": count,
            "language": "en",
            "format": "json",
        },
        user_agent=user_agent,
    )
    return payload.get("results", [])


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

def get_forecast(
    lat: float,
    lon: float,
    *,
    days: int = 7,
    user_agent: str,
) -> dict[str, Any]:
    """Fetch a daily Open-Meteo forecast for (lat, lon).

    Requests daily max/min temperature, precipitation sum, max wind speed
    and weather code, using timezone=auto so dates match the location.
    """
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude must be between -180 and 180, got {lon}")
    if not 1 <= days <= 16:
        raise ValueError(f"days must be between 1 and 16, got {days}")

    return request_json(
        FORECAST_URL,
        {
            "latitude": lat,
            "longitude": lon,
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,wind_speed_10m_max,weather_code"
            ),
            "timezone": "auto",
            "forecast_days": days,
        },
        user_agent=user_agent,
    )


def get_metno_forecast(lat: float, lon: float, *, user_agent: str) -> dict[str, Any]:
    """Fetch a MET Norway (compact GeoJSON) forecast for (lat, lon).

    Coordinates are rounded to 4 decimal places as required by MET Norway.
    """
    if not -90 <= lat <= 90:
        raise ValueError(f"Latitude must be between -90 and 90, got {lat}")
    if not -180 <= lon <= 180:
        raise ValueError(f"Longitude must be between -180 and 180, got {lon}")

    return request_json(
        METNO_URL,
        {"lat": round(lat, 4), "lon": round(lon, 4)},
        user_agent=user_agent,
    )


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def forecast_to_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert an Open-Meteo daily forecast payload into a tidy DataFrame.

    Columns: date, temp_max_C, temp_min_C, precip_mm, wind_max_kmh,
    weather_code, weather.
    """
    if "daily" not in payload:
        raise WeatherAPIError("Payload has no 'daily' section")

    daily = payload["daily"]
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(daily["time"]),
            "temp_max_C": daily["temperature_2m_max"],
            "temp_min_C": daily["temperature_2m_min"],
            "precip_mm": daily["precipitation_sum"],
            "wind_max_kmh": daily["wind_speed_10m_max"],
            "weather_code": daily["weather_code"],
        }
    )
    df["weather"] = df["weather_code"].map(WEATHER_CODES).fillna("Unknown")
    return df


def metno_to_dataframe(payload: dict[str, Any]) -> pd.DataFrame:
    """Convert a MET Norway compact payload into a small DataFrame of
    (time, air_temperature_C) for a quick cross-check with Open-Meteo.
    """
    try:
        timeseries = payload["properties"]["timeseries"]
    except (KeyError, TypeError) as exc:
        raise WeatherAPIError("Unexpected MET Norway payload shape") from exc

    rows = []
    for entry in timeseries:
        t = entry.get("time")
        temp = (
            entry.get("data", {})
            .get("instant", {})
            .get("details", {})
            .get("air_temperature")
        )
        if t is not None and temp is not None:
            rows.append({"time": pd.to_datetime(t), "air_temperature_C": temp})

    return pd.DataFrame(rows)