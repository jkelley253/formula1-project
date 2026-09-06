import json
from unittest.mock import patch

import pytest

from drivers_service.handlers.ec2_sync import load_local_settings, main
from drivers_service.infrastructure.postgres import upsert_drivers
from test_handler import DRIVER


@pytest.fixture
def configuration(tmp_path, monkeypatch):
    path = tmp_path / "database.json"
    path.write_text(json.dumps({
        "host": "127.0.0.1", "dbname": "formula1", "username": "driver_sync_ec2",
        "password": "test-secret",
    }))
    monkeypatch.setenv("DATABASE_CONFIG_FILE", str(path))
    return path


def test_local_settings(configuration):
    settings = load_local_settings()
    assert settings["host"] == "127.0.0.1"
    assert settings["port"] == 5432
    assert settings["user"] == "driver_sync_ec2"
    assert settings["password"] == "test-secret"
    assert settings["connect_timeout"] == 5


@pytest.mark.parametrize("payload", ["bad-json", "[]", "{}", '{"password":"test-secret"}'])
def test_invalid_configuration(configuration, payload):
    configuration.write_text(payload)
    with pytest.raises(ValueError):
        load_local_settings()


def test_ec2_success_uses_local_credentials(configuration, caplog):
    with patch("drivers_service.handlers.ec2_sync.fetch_sync_drivers", return_value=[DRIVER]), patch("drivers_service.handlers.ec2_sync.upsert_drivers", return_value=1) as write:
        caplog.set_level("INFO")
        assert main() == 0
    assert write.call_args.kwargs["connection_settings"]["user"] == "driver_sync_ec2"
    assert '"outcome": "success"' in caplog.text
    assert '"driver_count": 1' in caplog.text
    assert "duration_ms" in caplog.text
    assert "test-secret" not in caplog.text


def test_empty_result_skips_config_and_database():
    with patch("drivers_service.handlers.ec2_sync.fetch_sync_drivers", return_value=[]), patch("drivers_service.handlers.ec2_sync.load_local_settings") as load, patch("drivers_service.handlers.ec2_sync.upsert_drivers") as write:
        assert main() == 0
    load.assert_not_called()
    write.assert_not_called()


@pytest.mark.parametrize("stage", ["fetch_sync_drivers", "load_local_settings", "upsert_drivers"])
def test_failure_returns_nonzero_without_credentials(configuration, caplog, stage):
    with patch("drivers_service.handlers.ec2_sync.fetch_sync_drivers", return_value=[DRIVER]), patch(f"drivers_service.handlers.ec2_sync.{stage}", side_effect=RuntimeError("test-secret")):
        assert main() == 1
    assert '"outcome": "failed"' in caplog.text
    assert '"error_type": "RuntimeError"' in caplog.text
    assert "test-secret" not in caplog.text


def test_explicit_settings_bypass_secrets_manager():
    settings = {"host": "localhost", "dbname": "formula1"}
    with patch("drivers_service.infrastructure.postgres.get_connection_settings") as secret, patch("drivers_service.infrastructure.postgres.psycopg.connect") as connect:
        assert upsert_drivers([DRIVER], connection_settings=settings) == 1
    secret.assert_not_called()
    connect.assert_called_once_with(**settings)
