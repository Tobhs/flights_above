"""Config and options flow for Flights Above."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_COUNT,
    CONF_RADIUS,
    CONF_REQUIRE_ROUTE,
    CONF_SCAN_INTERVAL,
    DEFAULT_COUNT,
    DEFAULT_NAME,
    DEFAULT_RADIUS,
    DEFAULT_REQUIRE_ROUTE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_COUNT,
    MAX_RADIUS_KM,
    MAX_SCAN_INTERVAL,
    MIN_COUNT,
    MIN_SCAN_INTERVAL,
)


def _radius_selector() -> Any:
    return vol.All(vol.Coerce(float), vol.Range(min=1, max=MAX_RADIUS_KM))


def _count_selector() -> Any:
    return vol.All(vol.Coerce(int), vol.Range(min=MIN_COUNT, max=MAX_COUNT))


def _interval_selector() -> Any:
    return vol.All(
        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
    )


class FlightsAboveConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            unique_id = (
                f"{user_input[CONF_LATITUDE]:.4f}_"
                f"{user_input[CONF_LONGITUDE]:.4f}_"
                f"{user_input[CONF_RADIUS]}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME], data=user_input
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(
                    CONF_LATITUDE, default=self.hass.config.latitude
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE, default=self.hass.config.longitude
                ): vol.Coerce(float),
                vol.Required(CONF_RADIUS, default=DEFAULT_RADIUS): _radius_selector(),
                vol.Required(CONF_COUNT, default=DEFAULT_COUNT): _count_selector(),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): _interval_selector(),
                vol.Required(
                    CONF_REQUIRE_ROUTE, default=DEFAULT_REQUIRE_ROUTE
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return FlightsAboveOptionsFlow(config_entry)


class FlightsAboveOptionsFlow(config_entries.OptionsFlow):
    """Allow editing radius, count and update interval after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = {**self._entry.data, **self._entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RADIUS, default=opts.get(CONF_RADIUS, DEFAULT_RADIUS)
                ): _radius_selector(),
                vol.Required(
                    CONF_COUNT, default=opts.get(CONF_COUNT, DEFAULT_COUNT)
                ): _count_selector(),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): _interval_selector(),
                vol.Required(
                    CONF_REQUIRE_ROUTE,
                    default=opts.get(CONF_REQUIRE_ROUTE, DEFAULT_REQUIRE_ROUTE),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
