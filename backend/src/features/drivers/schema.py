"""
This module defines the data structure of a driver inside the application.
    What fields make up a Driver and what type should each field contain

This module does not:
    - retrieve data
    - transform upstream standings data
    - return JSON

References: 
    - https://www.formula1.com/en/drivers
    - https://docs.python.org/3.12/library/dataclasses.html
"""
# used to turn class into a data-oriented class without a manual constructor
from dataclasses import dataclass

# used to represent a driver's birthday independently of Pandas
from datetime import date

@dataclass
class DriverSchema:
    """
    Class to represent a driver in the format expected by the Drivers feature
    
    Inputs:
        - class constructor will eventually receive all the transformed driver field values
        - the service will create these objects

    Returns:
        - instance of the DriverSchema class

    Expected data types:
        position                 -> integer
        positionText             -> string
        points                   -> float
        wins                     -> integer
        driverId                 -> string
        driverNumber             -> integer
        driverCode               -> string
        driverUrl                -> string
        givenName                -> string
        familyName               -> string
        dateOfBirth              -> datetime.date
        driverNationality        -> string
        constructorIds           -> list[str]
        constructorUrls          -> list[str]
        constructorNames         -> list[str]
        constructorNationalities -> list[str]
    """
# CHAMPIONSHIP DATA
    # driver's numeric position for current championship
    drivers_current_position: int
    # driver's current position for championsip as str
    drivers_current_position_str: str
    # driver's current total championship points for the season
    drivers_current_total_points: float
    # drivers' current total amount of championsip wins for the season
    drivers_current_total_wins: int

# DRIVER IDENTITY
    # driver's identifier
    drivers_id: str
    # driver's racing number
    drivers_number: int
    # driver's driver code
    drivers_driver_code: str
    # driver's url reference
    drivers_driver_url: str
    # driver's first name
    drivers_first_name: str
    # driver's last name
    drivers_last_name: str
    # driver's birthday
    drivers_birthday: date
    # driver's nationality
    drivers_nationality: str

# CONSTRUCTOR DATA
    # driver's team constructor ids
    drivers_current_team_ids: list[str]
    # driver's team urls
    drivers_current_team_urls: list[str]
    # driver's current team names
    drivers_current_team_names: list[str]
    # driver's current team's nationalities
    drivers_current_team_nationalities: list[str]
