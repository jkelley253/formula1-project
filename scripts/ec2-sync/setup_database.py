"""Prepare the application table and a dedicated role without changing bootstrap credentials."""

import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql


def setup() -> None:
    config_path = Path("/config/database.json")
    expected = {"host": "127.0.0.1", "port": 5432, "dbname": "formula1", "username": "driver_sync_ec2"}
    admin = {
        "host": expected["host"], "port": 5432, "dbname": "formula1", "user": "postgres",
        "password": Path("/run/secrets/admin-password").read_text().strip(), "connect_timeout": 5,
    }
    with psycopg.connect(**admin) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (expected["username"],)
        ).fetchone()
        if config_path.exists():
            config = json.loads(config_path.read_text())
            if any(config.get(key) != value for key, value in expected.items()):
                raise ValueError("Existing configuration differs from installer defaults")
            if not isinstance(config.get("password"), str) or not config["password"]:
                raise ValueError("Existing configuration has no password")
        else:
            if exists:
                raise ValueError("Role exists but its local credentials are missing; restore the file")
            config = {**expected, "password": secrets.token_hex(32)}
            # Persist before role creation, allowing a failed setup to be retried.
            fd = os.open(config_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as file:
                json.dump(config, file)
                file.flush()
                os.fsync(file.fileno())
        if exists:
            # Refuse to silently rotate an existing role or take over its credentials.
            with psycopg.connect(**{**admin, "user": expected["username"], "password": config["password"]}):
                pass
        else:
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(expected["username"]), sql.Literal(config["password"])
            ))
        # Use the shared schema inside this transaction, without its outer wrapper.
        schema = Path("/setup/001_create_drivers.sql").read_text()
        connection.execute(schema.replace("BEGIN;", "").replace("COMMIT;", ""))
        role = sql.Identifier(expected["username"])
        for statement in (
            "GRANT CONNECT ON DATABASE formula1 TO {}",
            "GRANT USAGE ON SCHEMA public TO {}",
            "GRANT SELECT, INSERT, UPDATE ON TABLE public.drivers TO {}",
        ):
            connection.execute(sql.SQL(statement).format(role))
    print("Database setup complete: formula1.public.drivers, role driver_sync_ec2. Password not displayed.")


if __name__ == "__main__":
    try:
        setup()
    except Exception as exc:
        print(f"Database setup failed ({type(exc).__name__}); check database readiness and configuration. No credentials changed on an existing role.")
        raise SystemExit(1) from None
