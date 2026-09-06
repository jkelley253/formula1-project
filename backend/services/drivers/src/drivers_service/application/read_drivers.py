"""Serve stored standings maintained by the EC2 sync job."""

from drivers_service.domain.models import Driver
from drivers_service.infrastructure.driver_reader import read_drivers


def get_stored_drivers() -> list[Driver]:
    return read_drivers()
