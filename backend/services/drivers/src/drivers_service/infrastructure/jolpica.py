"""Jolpica standings API adapter."""

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.jolpi.ca/ergast/f1"


class StandingsServiceError(RuntimeError):
    """Raised when the upstream standings service cannot be used."""


def get_current_driver_standings() -> list[dict[str, Any]]:
    base_url = os.getenv("STANDINGS_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    request = Request(
        f"{base_url}/current/driverstandings.json",
        headers={"Accept": "application/json", "User-Agent": "formula1-project/1.0"},
    )

    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        lists = payload["MRData"]["StandingsTable"]["StandingsLists"]
        return lists[0]["DriverStandings"] if lists else []
    except (HTTPError, URLError, TimeoutError, KeyError, TypeError, ValueError) as exc:
        raise StandingsServiceError("Unable to retrieve current driver standings") from exc
