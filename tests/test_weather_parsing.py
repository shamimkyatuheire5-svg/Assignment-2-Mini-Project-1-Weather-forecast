from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.weather_api import (
    WEATHER_CODES,
    forecast_to_dataframe,
    geocode,
    get_forecast,
    metno_to_dataframe,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_sample(name: str) -> dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# DataFrame parsing tests
# ---------------------------------------------------------------------------

def test_forecast_dataframe_shape_and_columns():
    df = forecast_to_dataframe(load_sample("sample_forecast.json"))
    assert len(df) == 7
    assert list(df.columns) == [
        "date",
        "temp_max_C",
        "temp_min_C",
        "precip_mm",
        "wind_max_kmh",
        "weather_code",
        "weather",
    ]


def test_temperature_range_is_consistent():
    df = forecast_to_dataframe(load_sample("sample_forecast.json"))
    assert (df["temp_max_C"] >= df["temp_min_C"]).all()


def test_weather_codes_are_decoded():
    df = forecast_to_dataframe(load_sample("sample_forecast.json"))
    assert df["weather"].notna().all()
    assert df["weather_code"].isin(WEATHER_CODES).all()


def test_dates_are_datetime_and_sorted():
    df = forecast_to_dataframe(load_sample("sample_forecast.json"))
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert df["date"].is_monotonic_increasing


def test_units_are_encoded_in_column_names():
    df = forecast_to_dataframe(load_sample("sample_forecast.json"))
    assert "temp_max_C" in df.columns
    assert "precip_mm" in df.columns
    assert "wind_max_kmh" in df.columns


# ---------------------------------------------------------------------------
# Geocoding tests (offline — monkeypatch request_json)
# ---------------------------------------------------------------------------

def test_geocode_parses_candidates(monkeypatch):
    sample = load_sample("sample_geocode.json")

    def fake_request_json(url, params, **kwargs):
        return sample

    monkeypatch.setattr("src.weather_api.request_json", fake_request_json)
    results = geocode("Dresden", user_agent="test@example.com")
    assert len(results) == 1
    assert results[0]["name"] == "Dresden"
    assert results[0]["latitude"] == pytest.approx(51.05089)


def test_geocode_empty_name_raises():
    with pytest.raises(ValueError):
        geocode("", user_agent="test@example.com")


def test_geocode_zero_results(monkeypatch):
    monkeypatch.setattr(
        "src.weather_api.request_json",
        lambda *a, **k: {},  # no "results" key
    )
    assert geocode("Nowhereville", user_agent="test@example.com") == []


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------

def test_get_forecast_invalid_lat_raises():
    with pytest.raises(ValueError):
        get_forecast(999, 0, user_agent="test@example.com")


def test_get_forecast_invalid_lon_raises():
    with pytest.raises(ValueError):
        get_forecast(0, 999, user_agent="test@example.com")


def test_get_forecast_days_out_of_range():
    with pytest.raises(ValueError):
        get_forecast(51, 13, days=99, user_agent="test@example.com")


# ---------------------------------------------------------------------------
# MET Norway parsing test
# ---------------------------------------------------------------------------

def test_metno_parsing():
    payload = {
        "properties": {
            "timeseries": [
                {
                    "time": "2026-10-05T12:00:00Z",
                    "data": {"instant": {"details": {"air_temperature": 14.3}}},
                },
                {
                    "time": "2026-10-06T12:00:00Z",
                    "data": {"instant": {"details": {"air_temperature": 15.1}}},
                },
            ]
        }
    }
    df = metno_to_dataframe(payload)
    assert len(df) == 2
    assert "air_temperature_C" in df.columns
    assert df["air_temperature_C"].iloc[0] == pytest.approx(14.3)