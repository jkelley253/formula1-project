"""Domain models owned by the drivers service."""

from dataclasses import dataclass
from datetime import date


@dataclass
class Driver:
    drivers_current_position: int
    drivers_current_position_str: str
    drivers_current_total_points: float
    drivers_current_total_wins: int
    drivers_id: str
    drivers_number: int
    drivers_driver_code: str
    drivers_driver_url: str
    drivers_first_name: str
    drivers_last_name: str
    drivers_birthday: date
    drivers_nationality: str
    drivers_current_team_ids: list[str]
    drivers_current_team_urls: list[str]
    drivers_current_team_names: list[str]
    drivers_current_team_nationalities: list[str]
