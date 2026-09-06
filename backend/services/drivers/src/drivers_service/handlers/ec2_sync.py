"""One-shot EC2 job. Exit nonzero on failure so systemd reports failed runs."""

import json
import logging
import os
from pathlib import Path
from time import monotonic

from drivers_service.application.fetch_sync_drivers import fetch_sync_drivers
from drivers_service.infrastructure.postgres import upsert_drivers


def load_local_settings() -> dict:
    path = Path(os.environ.get("DATABASE_CONFIG_FILE", "/run/secrets/database.json"))
    config = json.loads(path.read_text())
    if not isinstance(config, dict):
        raise ValueError("Database configuration must be an object")
    for key in ("host", "dbname", "username", "password"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError("Invalid database configuration")
    port = config.get("port", 5432)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid database port")
    return {
        "host": config["host"], "port": port, "dbname": config["dbname"],
        "user": config["username"], "password": config["password"],
        # The installed job uses host networking and PostgreSQL on localhost.
        "sslmode": "prefer", "connect_timeout": 5,
        "options": "-c statement_timeout=15000 -c lock_timeout=5000",
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger(__name__)
    started = monotonic()
    try:
        drivers = fetch_sync_drivers()
        count = upsert_drivers(drivers, connection_settings=load_local_settings()) if drivers else 0
        result = {"outcome": "success" if drivers else "skipped", "driver_count": count}
    except Exception as exc:
        # Do not expose credential-bearing exception messages or tracebacks.
        logger.error(json.dumps({
            "outcome": "failed", "driver_count": 0, "error_type": type(exc).__name__,
            "duration_ms": round((monotonic() - started) * 1000),
        }))
        return 1
    result["duration_ms"] = round((monotonic() - started) * 1000)
    logger.info(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
