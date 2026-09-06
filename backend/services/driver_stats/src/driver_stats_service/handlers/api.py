"""Read-only API Gateway entry point."""

import logging
import psycopg

from formula1_lambda_common import json_response
from driver_stats_service.domain.stats import DRIVER_ID
from driver_stats_service.infrastructure.postgres import DriverNotFound, StatsUnavailable, read_profile


def lambda_handler(event, context):
    driver_id = (event.get("pathParameters") or {}).get("driver_id", "")
    if not isinstance(driver_id, str) or not DRIVER_ID.fullmatch(driver_id):
        return json_response(400, {"error": "Invalid driver ID"}, cache_control="no-store")
    try:
        return json_response(200, read_profile(driver_id))
    except DriverNotFound:
        return json_response(404, {"error": "Driver is not in the current season roster"}, cache_control="no-store")
    except StatsUnavailable:
        return json_response(503, {"error": "Driver statistics are awaiting their first update"}, cache_control="no-store")
    except (psycopg.Error, KeyError, ValueError, TypeError) as exc:
        logging.getLogger(__name__).error("Stats read failed (%s)", type(exc).__name__)
        return json_response(502, {"error": "Driver statistics are temporarily unavailable"}, cache_control="no-store")
