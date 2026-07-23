"""The Flights Above integration."""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import FlightsAboveCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

CARD_URL = "/flights_above/flights-above-card.js"
CARD_FILENAME = "flights-above-card.js"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Serve the bundled Lovelace card and register it as a frontend resource."""
    await _async_register_frontend(hass)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Expose the card JS at a stable URL and best-effort add the resource."""
    card_path = os.path.join(os.path.dirname(__file__), "lovelace", CARD_FILENAME)

    # Serve the file. Prefer the modern async API, fall back for older cores.
    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, card_path, False)]
        )
    except (ImportError, AttributeError):  # pragma: no cover - old HA cores
        hass.http.register_static_path(CARD_URL, card_path, False)

    # Best-effort: auto-add the Lovelace resource in storage mode so the card
    # works with no manual step. Harmless if it fails (YAML mode, older core).
    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None and isinstance(lovelace, dict):
            resources = lovelace.get("resources")
        if resources is None:
            return
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        versioned = f"{CARD_URL}?v=1.0.0"
        if any(
            (item.get("url") or "").split("?")[0] == CARD_URL
            for item in resources.async_items()
        ):
            return
        await resources.async_create_item({"res_type": "module", "url": versioned})
        _LOGGER.info("Registered Flights Above card resource at %s", versioned)
    except Exception as err:  # noqa: BLE001 - never block setup on this
        _LOGGER.debug(
            "Could not auto-register card resource (%s). Add %s manually if needed.",
            err,
            CARD_URL,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Flights Above from a config entry."""
    coordinator = FlightsAboveCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
