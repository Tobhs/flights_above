"""Sensor platform for Flights Above."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import FlightsAboveCoordinator

# Attributes copied straight from the flight dict onto a slot sensor.
_FLIGHT_ATTRS = (
    "registration",
    "aircraft_type",
    "latitude",
    "longitude",
    "altitude_ft",
    "ground_speed_kmh",
    "heading",
    "vertical_rate_fpm",
    "climb_status",
    "squawk",
    "emissions_class",
    "seats_typical",
    "people_on_board",
    "distance_km",
    "origin_name",
    "origin_iata",
    "origin_icao",
    "destination_name",
    "destination_iata",
    "destination_icao",
    "hours_flown",
    "hours_remaining",
    "hours_total",
    "eta",
    "progress_percent",
    "progress_bar",
    "co2_total_kg",
    "co2_so_far_kg",
    "co2_remaining_kg",
    "route_line",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the count sensor plus one sensor per flight slot."""
    coordinator: FlightsAboveCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [FlightsOverheadSensor(coordinator, entry)]
    for index in range(coordinator.count):
        entities.append(FlightSlotSensor(coordinator, entry, index))

    async_add_entities(entities)


class _BaseFlightsEntity(CoordinatorEntity[FlightsAboveCoordinator], SensorEntity):
    """Shared device grouping / attribution."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: FlightsAboveCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Flights Above",
            model="ADS-B overhead tracker",
        )


class FlightsOverheadSensor(_BaseFlightsEntity):
    """How many flights are currently within the configured radius."""

    _attr_icon = "mdi:airplane-search"
    _attr_name = "Flights Overhead"

    def __init__(
        self, coordinator: FlightsAboveCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_count"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict:
        flights = self.coordinator.data or []
        return {
            "radius_km": self.coordinator.radius_km,
            "latitude": self.coordinator.latitude,
            "longitude": self.coordinator.longitude,
            "flights": [
                {
                    "callsign": f["callsign"],
                    "origin": f["origin_iata"] or f["origin_icao"],
                    "destination": f["destination_iata"] or f["destination_icao"],
                    "route_line": f["route_line"],
                    "distance_km": f["distance_km"],
                    "co2_total_kg": f["co2_total_kg"],
                }
                for f in flights
            ],
        }


class FlightSlotSensor(_BaseFlightsEntity):
    """One of the last N flights that passed through the area."""

    _attr_icon = "mdi:airplane"

    def __init__(
        self,
        coordinator: FlightsAboveCoordinator,
        entry: ConfigEntry,
        index: int,
    ) -> None:
        super().__init__(coordinator, entry)
        self._index = index
        self._attr_name = f"Flight {index + 1}"
        self._attr_unique_id = f"{entry.entry_id}_flight_{index}"

    @property
    def _flight(self) -> dict | None:
        flights = self.coordinator.data or []
        if self._index < len(flights):
            return flights[self._index]
        return None

    @property
    def native_value(self) -> str | None:
        flight = self._flight
        return flight["callsign"] if flight else None

    @property
    def extra_state_attributes(self) -> dict:
        flight = self._flight
        if not flight:
            return {"in_range": False}
        attrs = {key: flight.get(key) for key in _FLIGHT_ATTRS}
        attrs["in_range"] = True
        return attrs
