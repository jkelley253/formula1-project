"""Read-only PostgreSQL access for the public drivers API."""

from dataclasses import fields
import logging
import math
import os

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from drivers_service.domain.models import Driver


logger = logging.getLogger(__name__)


class DriverReadError(RuntimeError):
    """Stored driver standings could not be read."""


def get_reader_connection_settings() -> dict:
    settings = {
        "host": os.environ["DRIVERS_DB_HOST"],
        "port": int(os.getenv("DRIVERS_DB_PORT", "5432")),
        "dbname": os.getenv("DRIVERS_DB_NAME", "formula1"),
        "user": os.environ["DRIVERS_DB_USER"],
        "password": os.environ["DRIVERS_DB_PASSWORD"],
        "sslmode": "prefer",
        "connect_timeout": 3,
        "options": "-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=2000",
    }
    if any(not settings[key] for key in ("host", "dbname", "user", "password")):
        raise ValueError("Missing reader configuration")
    if not 1 <= settings["port"] <= 65535:
        raise ValueError("Invalid database port")
    return settings


def read_drivers() -> list[Driver]:
    """Read one ordered snapshot; never fetch upstream or change database rows."""
    columns = sql.SQL(", ").join(sql.Identifier(field.name) for field in fields(Driver))
    query = sql.SQL(
        "SELECT {} FROM public.drivers ORDER BY drivers_current_position, drivers_id"
    ).format(columns)
    try:
        with psycopg.connect(**get_reader_connection_settings(), row_factory=dict_row) as connection:
            rows = connection.execute(query).fetchall()
        drivers = []
        for row in rows:
            # Preserve the frontend's numeric JSON contract for PostgreSQL NUMERIC.
            row["drivers_current_total_points"] = float(row["drivers_current_total_points"])
            if not math.isfinite(row["drivers_current_total_points"]):
                raise ValueError("Invalid stored points")
            drivers.append(Driver(**row))
        return drivers
    except (psycopg.Error, KeyError, TypeError, ValueError, OverflowError) as exc:
        logger.error("Driver database read failed (%s)", type(exc).__name__)
        raise DriverReadError("Stored driver standings are unavailable") from None
