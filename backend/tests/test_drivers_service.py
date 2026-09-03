from unittest.mock import patch

from features.drivers.service import get_current_drivers


STANDING = {
    "position": "2",
    "positionText": "2",
    "points": "87.5",
    "wins": "1",
    "Driver": {
        "driverId": "sample",
        "permanentNumber": "22",
        "code": "SMP",
        "url": "https://example.com/sample",
        "givenName": "Sample",
        "familyName": "Driver",
        "dateOfBirth": "1999-12-31",
        "nationality": "Example",
    },
    "Constructors": [{
        "constructorId": "sample-team",
        "url": "https://example.com/sample-team",
        "name": "Sample Team",
        "nationality": "Example",
    }],
}


@patch("features.drivers.service.get_current_driver_standings", return_value=[STANDING])
def test_service_maps_upstream_standing(client):
    driver = get_current_drivers()[0]

    assert driver.drivers_current_position == 2
    assert driver.drivers_current_total_points == 87.5
    assert driver.drivers_number == 22
    assert driver.drivers_birthday.isoformat() == "1999-12-31"
    assert driver.drivers_current_team_names == ["Sample Team"]
    client.assert_called_once_with()
