"""One-shot EC2 refresh/backfill with local and database overlap protection."""

import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import time

from driver_stats_service.application.sync import run_sync
from driver_stats_service.infrastructure.jolpica import Client, UpstreamError
from driver_stats_service.infrastructure.postgres import Store, connection_settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("refresh", "backfill", "rebuild"), nargs="?", default="refresh")
    parser.add_argument("--resume", action="store_true", help="Resume a matching interrupted run using its saved pages")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    started = time.monotonic()
    state = Path(os.getenv("STATS_STATE_DIR", "/state"))
    try:
        state.mkdir(parents=True, exist_ok=True)
        with (state / "sync.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with Store(connection_settings()) as store:
                result = run_sync(Client(state), store, mode=args.mode, resume=args.resume)
        result["duration_ms"] = round((time.monotonic() - started) * 1000)
        logging.info(json.dumps(result))
        return 0
    except Exception as exc:
        logging.error(json.dumps({"outcome": "failed", "error_type": type(exc).__name__,
                                  "reason": str(exc) if isinstance(exc, UpstreamError) else "Check configuration or source field validation",
                                  "duration_ms": round((time.monotonic() - started) * 1000)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
