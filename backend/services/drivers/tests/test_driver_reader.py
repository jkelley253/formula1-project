from dataclasses import asdict, replace
from decimal import Decimal
import json
import os
from unittest.mock import patch

import psycopg
import pytest

from drivers_service.handlers.api import lambda_handler
from drivers_service.infrastructure.driver_reader import (
    DriverReadError, get_reader_connection_settings, read_drivers,
)
from drivers_service.infrastructure.postgres import upsert_drivers
from test_handler import DRIVER
from test_sync_postgres import database  # Disposable database fixture.


def test_reader_settings(monkeypatch):
    monkeypatch.setenv("DRIVERS_DB_HOST", "172.31.40.120")
    monkeypatch.setenv("DRIVERS_DB_USER", "drivers_api")
    monkeypatch.setenv("DRIVERS_DB_PASSWORD", "private-test-value")
    settings = get_reader_connection_settings()
    assert settings["dbname"] == "formula1"
    assert settings["port"] == 5432
    assert settings["connect_timeout"] == 3
    assert "default_transaction_read_only=on" in settings["options"]


def test_missing_config_is_sanitized(monkeypatch, caplog):
    monkeypatch.delenv("DRIVERS_DB_HOST", raising=False)
    with pytest.raises(DriverReadError):
        read_drivers()
    assert "KeyError" in caplog.text


def test_database_failure_sanitized(caplog):
    with patch("drivers_service.infrastructure.driver_reader.get_reader_connection_settings", return_value={}), patch("drivers_service.infrastructure.driver_reader.psycopg.connect", side_effect=psycopg.OperationalError("private-test-value")):
        with pytest.raises(DriverReadError) as error:
            read_drivers()
    assert "private-test-value" not in caplog.text + str(error.value)


def test_empty_database_response():
    with patch("drivers_service.infrastructure.driver_reader.get_reader_connection_settings", return_value={}), patch("drivers_service.infrastructure.driver_reader.psycopg.connect") as connect:
        connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
        response = lambda_handler({}, None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"drivers": []}


def test_numeric_conversion_and_dates():
    row = {**asdict(DRIVER), "drivers_current_total_points": Decimal("87.5")}
    with patch("drivers_service.infrastructure.driver_reader.get_reader_connection_settings", return_value={}), patch("drivers_service.infrastructure.driver_reader.psycopg.connect") as connect:
        connect.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = [row]
        response = lambda_handler({}, None)
    driver = json.loads(response["body"])["drivers"][0]
    assert len(driver) == 16
    assert driver["drivers_current_total_points"] == 87.5
    assert driver["drivers_birthday"] == "2000-01-02"
    assert driver["drivers_current_team_names"] == ["Test Team"]


def test_reads_real_postgres_in_order_without_upstream_calls(database):
    second = replace(DRIVER, drivers_id="second", drivers_current_position=2,
                     drivers_current_total_points=87.5, drivers_current_team_names=["First", "Second"])
    tied = replace(DRIVER, drivers_id="another", drivers_current_position=1)
    upsert_drivers([second, DRIVER, tied])
    settings = {"conninfo": os.environ["DRIVER_SYNC_TEST_DSN"], "options": "-c default_transaction_read_only=on"}
    with patch("drivers_service.infrastructure.driver_reader.get_reader_connection_settings", return_value=settings), patch("drivers_service.infrastructure.jolpica.urlopen") as upstream, patch("drivers_service.application.fetch_sync_drivers.urlopen") as sync_upstream:
        response = lambda_handler({}, None)
    upstream.assert_not_called()
    sync_upstream.assert_not_called()
    assert response["statusCode"] == 200
    drivers = json.loads(response["body"])["drivers"]
    assert [d["drivers_id"] for d in drivers] == ["another", "test-driver", "second"]
    assert drivers[2]["drivers_current_total_points"] == 87.5
    assert drivers[2]["drivers_current_team_names"] == ["First", "Second"]
    assert all(len(d) == 16 for d in drivers)
    assert database.execute("SELECT count(*) FROM public.drivers").fetchone()[0] == 3
