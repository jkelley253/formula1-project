"""Independent standings fetch and mapping for the weekly database sync."""

import json
import math
import os
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from drivers_service.domain.models import Driver


class SyncStandingsError(RuntimeError):
    """The scheduled sync could not obtain valid standings."""


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected nonempty text")
    return value


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Expected an integer")
    return int(value)


def fetch_sync_drivers() -> list[Driver]:
    """Fetch all standings and validate every row before any database writes."""
    base_url = os.getenv(
        "STANDINGS_API_BASE_URL", "https://api.jolpi.ca/ergast/f1"
    ).rstrip("/")
    request = Request(
        f"{base_url}/current/driverstandings.json",
        headers={"Accept": "application/json", "User-Agent": "formula1-project/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        lists = payload["MRData"]["StandingsTable"]["StandingsLists"]
        if not isinstance(lists, list):
            raise ValueError("Expected standings lists")
        if not lists:
            return []
        standings = lists[0]["DriverStandings"]
        if not isinstance(standings, list):
            raise ValueError("Expected driver standings")
        drivers: list[Driver] = []
        seen: set[str] = set()
        for standing in standings:
            driver = standing["Driver"]
            constructors = standing.get("Constructors", [])
            if not isinstance(constructors, list):
                raise ValueError("Expected constructors list")
            points = float(standing["points"])
            if isinstance(standing["points"], bool) or not math.isfinite(points):
                raise ValueError("Expected finite points")
            driver_id = _text(driver["driverId"])
            if driver_id in seen:
                raise ValueError("Duplicate driver")
            seen.add(driver_id)
            drivers.append(
                Driver(
                    drivers_current_position=_integer(standing["position"]),
                    drivers_current_position_str=_text(standing["positionText"]),
                    drivers_current_total_points=points,
                    drivers_current_total_wins=_integer(standing["wins"]),
                    drivers_id=driver_id,
                    drivers_number=_integer(driver["permanentNumber"]),
                    drivers_driver_code=_text(driver["code"]),
                    drivers_driver_url=_text(driver["url"]),
                    drivers_first_name=_text(driver["givenName"]),
                    drivers_last_name=_text(driver["familyName"]),
                    drivers_birthday=date.fromisoformat(driver["dateOfBirth"]),
                    drivers_nationality=_text(driver["nationality"]),
                    drivers_current_team_ids=[_text(c["constructorId"]) for c in constructors],
                    drivers_current_team_urls=[_text(c["url"]) for c in constructors],
                    drivers_current_team_names=[_text(c["name"]) for c in constructors],
                    drivers_current_team_nationalities=[_text(c["nationality"]) for c in constructors],
                )
            )
        return drivers
    except (HTTPError, URLError, TimeoutError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise SyncStandingsError("Unable to fetch valid driver standings") from exc
