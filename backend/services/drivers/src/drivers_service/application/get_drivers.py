"""Retrieve and map current driver standings."""

from datetime import date

from drivers_service.domain.models import Driver
from drivers_service.infrastructure.jolpica import get_current_driver_standings


def get_current_drivers() -> list[Driver]:
    standings = get_current_driver_standings()
    drivers: list[Driver] = []
    for standing in standings:
        driver = standing["Driver"]
        constructors = standing.get("Constructors", [])
        drivers.append(
            Driver(
                drivers_current_position=int(standing["position"]),
                drivers_current_position_str=standing["positionText"],
                drivers_current_total_points=float(standing["points"]),
                drivers_current_total_wins=int(standing["wins"]),
                drivers_id=driver["driverId"],
                drivers_number=int(driver["permanentNumber"]),
                drivers_driver_code=driver["code"],
                drivers_driver_url=driver["url"],
                drivers_first_name=driver["givenName"],
                drivers_last_name=driver["familyName"],
                drivers_birthday=date.fromisoformat(driver["dateOfBirth"]),
                drivers_nationality=driver["nationality"],
                drivers_current_team_ids=[item["constructorId"] for item in constructors],
                drivers_current_team_urls=[item["url"] for item in constructors],
                drivers_current_team_names=[item["name"] for item in constructors],
                drivers_current_team_nationalities=[item["nationality"] for item in constructors],
            )
        )
    return drivers
