"""Idempotent administrator setup; application processes never receive admin credentials."""

import json
import os
from pathlib import Path
import secrets

import psycopg
from psycopg import sql


def setup():
    admin = {"host": "127.0.0.1", "port": 5432, "dbname": "formula1", "user": "postgres",
             "password": Path("/run/secrets/admin-password").read_text().strip(), "connect_timeout": 5}
    with psycopg.connect(**admin) as conn:
        conn.execute(Path("/setup/schema.sql").read_text().replace("BEGIN;", "").replace("COMMIT;", ""))
        for role, filename in (("driver_stats_sync", "database.json"), ("driver_stats_api", "reader.json")):
            path = Path("/config") / filename
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (role,)).fetchone()
            if path.exists():
                config = json.loads(path.read_text())
                if config.get("username") != role or config.get("dbname") != "formula1" or not config.get("password"):
                    raise ValueError("Invalid saved credentials")
            else:
                if exists:
                    raise ValueError("Role exists without its saved credential file")
                config = {"host": "127.0.0.1", "port": 5432, "dbname": "formula1", "username": role, "password": secrets.token_hex(32)}
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as file:
                    json.dump(config, file)
                    file.flush()
                    os.fsync(file.fileno())
            if exists:
                with psycopg.connect(**{**admin, "user": role, "password": config["password"]}):
                    pass
            else:
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(role), sql.Literal(config["password"])))
            if any(conn.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=%s", (role,)).fetchone()):
                raise ValueError("Application role has elevated privileges")
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE formula1 TO {}").format(sql.Identifier(role)))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA driver_stats TO {}").format(sql.Identifier(role)))
            tables = ("standings", "season_stats", "career_stats") if role == "driver_stats_api" else ("results", "standings", "season_stats", "career_stats", "sync_runs")
            privileges = sql.SQL("SELECT") if role == "driver_stats_api" else sql.SQL("SELECT, INSERT, UPDATE, DELETE")
            for table in tables:
                conn.execute(sql.SQL("GRANT {} ON driver_stats.{} TO {}").format(privileges, sql.Identifier(table), sql.Identifier(role)))
            if role == "driver_stats_api":
                conn.execute("ALTER ROLE driver_stats_api SET default_transaction_read_only=on")
                for table in ("results", "standings", "season_stats", "career_stats", "sync_runs"):
                    if conn.execute("SELECT has_table_privilege(%s,%s,'INSERT,UPDATE,DELETE,TRUNCATE')", (role, f"driver_stats.{table}")).fetchone()[0]:
                        raise ValueError("Reader must not have write privileges")
            if conn.execute("SELECT to_regclass('public.drivers')").fetchone()[0] and conn.execute(
                "SELECT has_table_privilege(%s,'public.drivers','INSERT,UPDATE,DELETE,TRUNCATE')", (role,)).fetchone()[0]:
                raise ValueError("Stats role must not write driver records")
    print("Driver stats tables and separate reader/writer credentials are ready.")


if __name__ == "__main__":
    try:
        setup()
    except Exception as exc:
        print(f"Driver stats setup failed ({type(exc).__name__}); credentials were not displayed.")
        raise SystemExit(1) from None
