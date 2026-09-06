"""Create a separate SELECT-only API role. Run inside the installed sync image."""

import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql


def setup() -> None:
    path = Path("/config/reader.json")
    admin = {
        "host": "127.0.0.1", "port": 5432, "dbname": "formula1", "user": "postgres",
        "password": Path("/run/secrets/admin-password").read_text().strip(), "connect_timeout": 5,
    }
    with psycopg.connect(**admin) as connection:
        if connection.execute("SELECT to_regclass('public.drivers')").fetchone()[0] is None:
            raise ValueError("Run the EC2 writer setup first")
        exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname = 'drivers_api'").fetchone()
        if path.exists():
            config = json.loads(path.read_text())
            if config.get("username") != "drivers_api" or config.get("dbname") != "formula1" or not config.get("password"):
                raise ValueError("Invalid saved reader credentials")
        else:
            if exists:
                raise ValueError("Reader role already exists; restore its saved credentials")
            config = {"username": "drivers_api", "dbname": "formula1", "password": secrets.token_hex(32)}
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as file:
                json.dump(config, file)
                file.flush()
                os.fsync(file.fileno())
        if exists:
            with psycopg.connect(**{**admin, "user": "drivers_api", "password": config["password"]}):
                pass
        else:
            connection.execute(sql.SQL("CREATE ROLE drivers_api LOGIN PASSWORD {}").format(sql.Literal(config["password"])))
        connection.execute("GRANT CONNECT ON DATABASE formula1 TO drivers_api")
        connection.execute("GRANT USAGE ON SCHEMA public TO drivers_api")
        connection.execute("GRANT SELECT ON public.drivers TO drivers_api")
        connection.execute("ALTER ROLE drivers_api SET default_transaction_read_only = on")
        # Do not silently accept a previously privileged role as the API account.
        privileges = connection.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname = 'drivers_api'"
        ).fetchone()
        if any(privileges):
            raise ValueError("API role has elevated privileges")
        if connection.execute("SELECT has_table_privilege('drivers_api', 'public.drivers', 'INSERT,UPDATE,DELETE,TRUNCATE')").fetchone()[0]:
            raise ValueError("API role must not have write privileges")
    print("Reader role ready: drivers_api has SELECT access; credentials saved without displaying them.")


if __name__ == "__main__":
    try:
        setup()
    except Exception as exc:
        print(f"Reader setup failed ({type(exc).__name__}); inspect configuration and role privileges.")
        raise SystemExit(1) from None
