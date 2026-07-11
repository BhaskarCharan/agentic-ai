"""Tools for the weather specialist agent (see `weather_agent.py`).

Uses Open-Meteo - free, no API key, no OAuth/consent needed (unlike Gmail/
LinkedIn), which is exactly why weather was picked as the first specialist:
it proves the supervisor + specialist-agent-as-tool pattern with nothing
else that can go wrong.
"""

import httpx
from langchain_core.tools import tool

_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


@tool
async def get_current_weather(city: str) -> str:
    """Get the current weather for a city name (e.g. "Hyderabad", "London").

    Geocodes the city name to coordinates first, then fetches current
    conditions. Returns a short plain-text summary.
    """
    async with httpx.AsyncClient() as client:
        geo = await client.get(_GEOCODING_URL, params={"name": city, "count": 1})
        results = geo.json().get("results")
        if not results:
            return f"Could not find a location matching '{city}'."

        location = results[0]
        forecast = await client.get(
            _FORECAST_URL,
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m",
            },
        )
        current = forecast.json()["current"]

    return (
        f"Current weather in {location['name']}: {current['temperature_2m']}°C, "
        f"{current['relative_humidity_2m']}% humidity, "
        f"wind {current['wind_speed_10m']} km/h."
    )


WEATHER_TOOLS = [get_current_weather]
