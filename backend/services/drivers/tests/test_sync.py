import copy
import io
import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from drivers_service.application.fetch_sync_drivers import SyncStandingsError, fetch_sync_drivers
from drivers_service.application.get_drivers import get_current_drivers
from drivers_service.handlers.sync import lambda_handler
from drivers_service.infrastructure.postgres import get_connection_settings, upsert_drivers
from test_get_drivers import STANDING
from test_handler import DRIVER


def upstream(standings):
    return io.BytesIO(json.dumps({
        "MRData": {"StandingsTable": {"StandingsLists": [{"DriverStandings": standings}]}}
    }).encode())


def test_all_fields_match_existing_mapping(monkeypatch):
    standing = copy.deepcopy(STANDING)
    standing["Constructors"].append({
        "constructorId": "second", "url": "https://example.com/second",
        "name": "Second", "nationality": "Another",
    })
    monkeypatch.setenv("STANDINGS_API_BASE_URL", "https://example.com/f1/")
    with patch("drivers_service.application.fetch_sync_drivers.urlopen", return_value=upstream([standing])) as fetch:
        actual = fetch_sync_drivers()
    with patch("drivers_service.application.get_drivers.get_current_driver_standings", return_value=[standing]):
        expected = get_current_drivers()
    assert asdict(actual[0]) == asdict(expected[0])
    assert len(asdict(actual[0])) == 16
    assert fetch.call_args.args[0].full_url == "https://example.com/f1/current/driverstandings.json"
    assert fetch.call_args.kwargs == {"timeout": 10}


@pytest.mark.parametrize("field,value", [("points", "NaN"), ("position", "bad"), ("wins", 1.5), ("Constructors", None)])
def test_malformed_later_driver_rejects_entire_batch(field, value):
    bad = copy.deepcopy(STANDING)
    bad["Driver"]["driverId"] = "second"
    bad[field] = value
    with patch("drivers_service.application.fetch_sync_drivers.urlopen", return_value=upstream([STANDING, bad])):
        with pytest.raises(SyncStandingsError):
            fetch_sync_drivers()


@pytest.mark.parametrize("payload", [b"not json", b"{}", b'{"MRData":{"StandingsTable":{"StandingsLists":null}}}'])
def test_invalid_payload(payload):
    with patch("drivers_service.application.fetch_sync_drivers.urlopen", return_value=io.BytesIO(payload)):
        with pytest.raises(SyncStandingsError):
            fetch_sync_drivers()


def test_upstream_failure():
    with patch("drivers_service.application.fetch_sync_drivers.urlopen", side_effect=URLError("offline")):
        with pytest.raises(SyncStandingsError):
            fetch_sync_drivers()


@pytest.mark.parametrize("lists", [[], [{"DriverStandings": []}]])
def test_empty_standings(lists):
    payload = {"MRData": {"StandingsTable": {"StandingsLists": lists}}}
    with patch("drivers_service.application.fetch_sync_drivers.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
        assert fetch_sync_drivers() == []


def test_duplicate_driver_rejected():
    with patch("drivers_service.application.fetch_sync_drivers.urlopen", return_value=upstream([STANDING, STANDING])):
        with pytest.raises(SyncStandingsError):
            fetch_sync_drivers()


def test_empty_sync_skips_database(caplog):
    with patch("drivers_service.handlers.sync.fetch_sync_drivers", return_value=[]), patch("drivers_service.handlers.sync.upsert_drivers") as write:
        result = lambda_handler({}, None)
    write.assert_not_called()
    assert result["outcome"] == "skipped"
    assert result["driver_count"] == 0
    assert "duration_ms" in caplog.text


def test_successful_handler():
    with patch("drivers_service.handlers.sync.fetch_sync_drivers", return_value=[DRIVER]), patch("drivers_service.handlers.sync.upsert_drivers", return_value=1) as write:
        assert lambda_handler({}, None)["driver_count"] == 1
    write.assert_called_once_with([DRIVER])


@pytest.mark.parametrize("stage", ["fetch_sync_drivers", "upsert_drivers"])
def test_failure_is_raised_without_sensitive_details(stage, caplog):
    with patch("drivers_service.handlers.sync.fetch_sync_drivers", return_value=[DRIVER]), patch("drivers_service.handlers.sync.upsert_drivers") as write:
        with patch(f"drivers_service.handlers.sync.{stage}", side_effect=RuntimeError("secret-password")):
            with pytest.raises(RuntimeError, match="Driver sync failed") as error:
                lambda_handler({}, None)
        if stage == "fetch_sync_drivers":
            write.assert_not_called()
    assert "secret-password" not in str(error.value) + caplog.text
    assert error.value.__suppress_context__


SECRET = {"host": "db.internal", "dbname": "formula1", "username": "driver_sync", "password": "secret-password"}


def test_secret_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_SECRET_ARN", "test-secret")
    with patch("drivers_service.infrastructure.postgres.boto3.client") as client:
        client.return_value.get_secret_value.return_value = {"SecretString": json.dumps(SECRET)}
        settings = get_connection_settings()
    assert settings["port"] == 5432
    assert settings["sslmode"] == "prefer"
    assert settings["user"] == "driver_sync"
    client.return_value.get_secret_value.assert_called_once_with(SecretId="test-secret")


@pytest.mark.parametrize("secret", [{}, [], {**SECRET, "port": 0}, {**SECRET, "password": None}, {**SECRET, "sslmode": "invalid"}])
def test_invalid_secret(monkeypatch, secret):
    monkeypatch.setenv("DATABASE_SECRET_ARN", "test-secret")
    with patch("drivers_service.infrastructure.postgres.boto3.client") as client:
        client.return_value.get_secret_value.return_value = {"SecretString": json.dumps(secret)}
        with pytest.raises(ValueError):
            get_connection_settings()


def test_secret_access_failure(monkeypatch):
    monkeypatch.setenv("DATABASE_SECRET_ARN", "test-secret")
    with patch("drivers_service.infrastructure.postgres.boto3.client") as client:
        client.return_value.get_secret_value.side_effect = RuntimeError("denied")
        with pytest.raises(RuntimeError):
            get_connection_settings()


def test_empty_writer_never_connects():
    with patch("drivers_service.infrastructure.postgres.psycopg.connect") as connect:
        assert upsert_drivers([]) == 0
    connect.assert_not_called()


def test_database_failure_exits_transaction_with_exception():
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.executemany.side_effect = RuntimeError("write failed")
    with patch("drivers_service.infrastructure.postgres.get_connection_settings", return_value={}), patch("drivers_service.infrastructure.postgres.psycopg.connect") as connect:
        connect.return_value.__enter__.return_value = connection
        with pytest.raises(RuntimeError):
            upsert_drivers([DRIVER])
        assert connect.return_value.__exit__.call_args.args[0] is RuntimeError
