"""Weekly EventBridge Scheduler entrypoint."""

import json
import logging
from time import monotonic
from typing import Any

from drivers_service.application.fetch_sync_drivers import fetch_sync_drivers
from drivers_service.infrastructure.postgres import upsert_drivers


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    del event, context
    started = monotonic()
    count = 0
    try:
        drivers = fetch_sync_drivers()
        count = upsert_drivers(drivers) if drivers else 0
        result = {"outcome": "success" if drivers else "skipped", "driver_count": count}
    except Exception as exc:
        # Exception messages and tracebacks can contain connection credentials.
        logger.error(json.dumps({
            "outcome": "failed", "driver_count": 0,
            "error_type": type(exc).__name__,
            "duration_ms": round((monotonic() - started) * 1000),
        }))
        raise RuntimeError("Driver sync failed; see sanitized outcome log") from None
    result["duration_ms"] = round((monotonic() - started) * 1000)
    logger.info(json.dumps(result))
    return result
