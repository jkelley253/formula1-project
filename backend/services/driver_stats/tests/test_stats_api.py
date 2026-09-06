import json
import psycopg
import pytest

from driver_stats_service.handlers import api
from driver_stats_service.infrastructure.postgres import DriverNotFound, StatsUnavailable


@pytest.mark.parametrize("driver", ["../foo", "a/b", "", "UPPER", None, "a" * 81])
def test_invalid_id_never_reads_database(monkeypatch, driver):
    monkeypatch.setattr(api, "read_profile", lambda *args: pytest.fail("Unexpected database access"))
    assert api.lambda_handler({"pathParameters": {"driver_id": driver}}, None)["statusCode"] == 400


@pytest.mark.parametrize("error,status", [(DriverNotFound(), 404), (StatsUnavailable(), 503), (psycopg.OperationalError("secret"), 502)])
def test_errors_are_sanitized(monkeypatch, error, status, caplog):
    def read(*args):
        raise error
    monkeypatch.setattr(api, "read_profile", read)
    response = api.lambda_handler({"pathParameters": {"driver_id": "hamilton"}}, None)
    assert response["statusCode"] == status
    assert response["headers"]["cache-control"] == "no-store"
    assert "secret" not in response["body"] + caplog.text


def test_success_preserves_snapshot(monkeypatch):
    monkeypatch.setattr(api, "read_profile", lambda _: {"driver_id": "hamilton", "updated_at": "2026-08-01T00:00:00+00:00"})
    response = api.lambda_handler({"pathParameters": {"driver_id": "hamilton"}}, None)
    assert response["statusCode"] == 200
    assert json.loads(response["body"])["updated_at"] == "2026-08-01T00:00:00+00:00"
