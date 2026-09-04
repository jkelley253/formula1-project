import json
from datetime import date

from formula1_lambda_common.http import json_response


def test_json_response_serializes_dates_and_standard_headers(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGIN", "https://formula1project.com")

    response = json_response(200, {"date": date(2026, 3, 8)})

    assert response["statusCode"] == 200
    assert response["headers"] == {
        "content-type": "application/json",
        "access-control-allow-origin": "https://formula1project.com",
        "cache-control": "public, max-age=300",
    }
    assert json.loads(response["body"]) == {"date": "2026-03-08"}


def test_json_response_uses_wildcard_cors_by_default(monkeypatch):
    monkeypatch.delenv("CORS_ALLOW_ORIGIN", raising=False)

    response = json_response(502, {"error": "unavailable"})

    assert response["headers"]["access-control-allow-origin"] == "*"
