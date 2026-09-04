"""HTTP response helpers shared by API Gateway Lambda handlers."""

import json
import os
from datetime import date
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def json_response(
    status_code: int,
    body: dict[str, Any],
    *,
    cache_control: str = "public, max-age=300",
) -> dict[str, Any]:
    """Build an API Gateway HTTP API response with standard service headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "access-control-allow-origin": os.getenv("CORS_ALLOW_ORIGIN", "*"),
            "cache-control": cache_control,
        },
        "body": json.dumps(body, default=_json_default, separators=(",", ":")),
    }
