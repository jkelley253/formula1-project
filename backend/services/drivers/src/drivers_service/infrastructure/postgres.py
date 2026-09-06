"""Secrets Manager configuration and transactional driver upserts."""

import json
import os
from dataclasses import asdict, fields
from decimal import Decimal
from typing import Any

import boto3
import psycopg
from botocore.config import Config
from psycopg import sql

from drivers_service.domain.models import Driver


def get_connection_settings() -> dict[str, Any]:
    """Read credentials per invocation so secret rotation requires no redeploy."""
    client = boto3.client(
        "secretsmanager",
        config=Config(connect_timeout=5, read_timeout=5, retries={"total_max_attempts": 2}),
    )
    response = client.get_secret_value(SecretId=os.environ["DATABASE_SECRET_ARN"])
    secret = json.loads(response["SecretString"])
    if not isinstance(secret, dict):
        raise ValueError("Database secret must be a JSON object")
    for key in ("host", "dbname", "username", "password"):
        if not isinstance(secret.get(key), str) or not secret[key]:
            raise ValueError("Database secret has missing or invalid required fields")
    port = secret.get("port", 5432)
    if isinstance(port, bool) or not isinstance(port, (int, str)):
        raise ValueError("Invalid database port")
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("Invalid database port")
    sslmode = secret.get("sslmode", "prefer")
    if sslmode not in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
        raise ValueError("Invalid database SSL mode")
    return {
        "host": secret["host"], "port": port, "dbname": secret["dbname"],
        "user": secret["username"], "password": secret["password"],
        "sslmode": sslmode, "connect_timeout": 5,
        "options": "-c statement_timeout=15000 -c lock_timeout=5000",
    }


def upsert_drivers(
    drivers: list[Driver], *, connection_settings: dict[str, Any] | None = None
) -> int:
    if not drivers:
        return 0
    columns = [field.name for field in fields(Driver)]
    query = sql.SQL(
        "INSERT INTO public.drivers ({columns}) VALUES ({values}) "
        "ON CONFLICT (drivers_id) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP"
    ).format(
        columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
        values=sql.SQL(", ").join(sql.Placeholder(name) for name in columns),
        updates=sql.SQL(", ").join(
            sql.SQL("{col} = EXCLUDED.{col}").format(col=sql.Identifier(name))
            for name in columns if name != "drivers_id"
        ),
    )
    rows = [asdict(driver) for driver in drivers]
    for row in rows:
        row["drivers_current_total_points"] = Decimal(str(row["drivers_current_total_points"]))
    # Connection context commits on success, rolls back on failure, and closes.
    settings = get_connection_settings() if connection_settings is None else connection_settings
    with psycopg.connect(**settings) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(query, rows)
    return len(rows)
