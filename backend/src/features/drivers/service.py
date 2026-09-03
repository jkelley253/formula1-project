"""Map upstream standings records into the application's driver schema."""
from datetime import date

from integrations.jolpica.client import get_current_driver_standings
from features.drivers.schema import DriverSchema

def get_current_drivers() -> list[DriverSchema]:
    """Retrieve and map current standings into the application's driver schema."""
    standings = get_current_driver_standings()
    drivers: list[DriverSchema] = []
    for standing in standings:
        driver = standing["Driver"]
        constructors = standing.get("Constructors", [])
        current_driver = DriverSchema(
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
        drivers.append(current_driver)
    return drivers
