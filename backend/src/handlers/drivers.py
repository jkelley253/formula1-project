import json
import os
from dataclasses import asdict
from datetime import date
from typing import Any

from features.drivers.service import get_current_drivers
from integrations.jolpica.client import StandingsServiceError


def _json_default(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": os.getenv("CORS_ALLOW_ORIGIN", "*"),
            "cache-control": "public, max-age=300",
        },
        "body": json.dumps(body, default=_json_default, separators=(",", ":")),
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle API Gateway HTTP API requests for the current driver standings."""
    del event, context
    try:
        drivers = [asdict(driver) for driver in get_current_drivers()]
    except StandingsServiceError:
        return _response(502, {"error": "Driver standings are temporarily unavailable"})
    return _response(200, {"drivers": drivers})
