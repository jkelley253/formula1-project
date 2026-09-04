"""API Gateway Lambda handlers for the drivers service."""

from dataclasses import asdict
from typing import Any

from drivers_service.application.get_drivers import get_current_drivers
from drivers_service.infrastructure.jolpica import StandingsServiceError
from formula1_lambda_common import json_response


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Return the current Formula 1 driver standings."""
    del event, context
    try:
        drivers = [asdict(driver) for driver in get_current_drivers()]
    except StandingsServiceError:
        return json_response(
            502, {"error": "Driver standings are temporarily unavailable"}
        )
    return json_response(200, {"drivers": drivers})
