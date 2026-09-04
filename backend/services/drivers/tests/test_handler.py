import json
from datetime import date
from unittest.mock import patch

from drivers_service.domain.models import Driver
from drivers_service.handlers.api import lambda_handler
from drivers_service.infrastructure.jolpica import StandingsServiceError


DRIVER = Driver(
    drivers_current_position=1,
    drivers_current_position_str="1",
    drivers_current_total_points=100.0,
    drivers_current_total_wins=3,
    drivers_id="test-driver",
    drivers_number=1,
    drivers_driver_code="TST",
    drivers_driver_url="https://example.com/driver",
    drivers_first_name="Test",
    drivers_last_name="Driver",
    drivers_birthday=date(2000, 1, 2),
    drivers_nationality="Test",
    drivers_current_team_ids=["test-team"],
    drivers_current_team_urls=["https://example.com/team"],
    drivers_current_team_names=["Test Team"],
    drivers_current_team_nationalities=["Test"],
)


@patch("drivers_service.handlers.api.get_current_drivers", return_value=[DRIVER])
def test_handler_preserves_api_contract(get_drivers):
    response = lambda_handler({}, None)

    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    assert response["headers"]["cache-control"] == "public, max-age=300"
    assert json.loads(response["body"]) == {
        "drivers": [{**DRIVER.__dict__, "drivers_birthday": "2000-01-02"}]
    }
    get_drivers.assert_called_once_with()


@patch(
    "drivers_service.handlers.api.get_current_drivers",
    side_effect=StandingsServiceError("upstream failed"),
)
def test_handler_returns_bad_gateway_when_upstream_is_unavailable(get_drivers):
    response = lambda_handler({}, None)

    assert response["statusCode"] == 502
    assert json.loads(response["body"]) == {
        "error": "Driver standings are temporarily unavailable"
    }
    get_drivers.assert_called_once_with()
