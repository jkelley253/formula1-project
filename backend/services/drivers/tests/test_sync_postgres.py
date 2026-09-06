"""Opt-in integration tests. DRIVER_SYNC_TEST_DSN must name a disposable database."""

import os
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest

from drivers_service.infrastructure.postgres import upsert_drivers
from test_handler import DRIVER


@pytest.fixture
def database():
    dsn = os.getenv("DRIVER_SYNC_TEST_DSN")
    if not dsn:
        pytest.skip("Set DRIVER_SYNC_TEST_DSN to a disposable PostgreSQL database")
    with psycopg.connect(dsn, autocommit=True) as conn:
        # Never remove an existing table: refuse a nonempty test database.
        assert conn.execute("SELECT to_regclass('public.drivers')").fetchone()[0] is None
        conn.execute((Path(__file__).parents[1] / "sql/001_create_drivers.sql").read_text())
        try:
            with patch("drivers_service.infrastructure.postgres.get_connection_settings", return_value={"conninfo": dsn}):
                yield conn
        finally:
            conn.execute("DROP TABLE public.drivers")


def test_insert_update_retry_and_native_types(database):
    driver = replace(DRIVER, drivers_current_total_points=87.5,
                     drivers_current_team_names=["First", "O'Brien"],
                     drivers_current_team_ids=["first", "second"])
    assert upsert_drivers([driver]) == 1
    first_time = database.execute("SELECT updated_at FROM public.drivers").fetchone()[0]
    updated = replace(driver, drivers_current_total_points=101.5, drivers_current_position=2)
    assert upsert_drivers([updated]) == 1
    assert upsert_drivers([updated]) == 1
    row = database.execute("SELECT drivers_current_total_points, drivers_current_position, drivers_birthday, drivers_current_team_names, updated_at FROM public.drivers").fetchone()
    assert row[:4] == (Decimal("101.5"), 2, date(2000, 1, 2), ["First", "O'Brien"])
    assert row[4] >= first_time
    assert row[4].tzinfo is not None
    assert database.execute("SELECT count(*) FROM public.drivers").fetchone()[0] == 1
    upsert_drivers([replace(driver, drivers_id="another", drivers_current_team_names=[])])
    assert database.execute("SELECT count(*) FROM public.drivers").fetchone()[0] == 2
    assert upsert_drivers([]) == 0
    assert database.execute("SELECT count(*) FROM public.drivers").fetchone()[0] == 2


def test_entire_batch_rolls_back(database):
    upsert_drivers([DRIVER])
    invalid = replace(DRIVER, drivers_id="invalid", drivers_first_name=None)
    with pytest.raises(psycopg.errors.NotNullViolation):
        upsert_drivers([replace(DRIVER, drivers_current_total_points=999), invalid])
    assert database.execute("SELECT drivers_current_total_points FROM public.drivers").fetchall() == [(Decimal("100"),)]
