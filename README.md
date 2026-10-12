# Mini-Project 1: Fetching and Displaying a Weather Forecast

## Overview
Fetch a weather forecast for any city using Open-Meteo (geocoding + forecast) and MET Norway as a second source, then display it as a table, chart and text summary.

## Setup
python -m venv myenv
.\myenv\Scripts\Activate.ps1
pip install -r requirements.txt

## Run
jupyter notebook notebooks/project1_weather.ipynb
Restart & Run All to reproduce.

## Project structure
- notebooks/  → executable notebook (Part A–D)
- src/        → reusable logic (weather_api.py)
- tests/      → offline pytest checks
- data/       → saved sample JSON used by tests

## Findings
- Open-Meteo geocoding + forecast work without an API key.
- MET Norway requires a valid User-Agent with contact email.
- Retry with exponential backoff handles transient 5xx errors.
- Saved sample JSON makes tests reproducible offline.

## AI use declaration
I used an AI assistant for scaffolding, docstrings, and debugging venv issues. All code was reviewed, tested, and understood by me.

## Data sources
- Open-Meteo Geocoding — https://geocoding-api.open-meteo.com/v1/search
- Open-Meteo Forecast — https://api.open-meteo.com/v1/forecast
- MET Norway Locationforecast 2.0 — https://api.met.no/weatherapi/locationforecast/2.0