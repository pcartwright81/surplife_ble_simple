"""Config flow for Surplife BLE Simple integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth

from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SERVICE_UUID

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Surplife BLE Simple."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_devices: dict[str, bluetooth.BluetoothServiceInfoBleak] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the user step to pick discovered device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input["address"]
            discovery_info = self._discovered_devices.get(address)
            if discovery_info:
                await self.async_set_unique_id(address, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=discovery_info.name,
                    data={"address": address},
                )
            errors["base"] = "cannot_connect"

        # Scan for devices with specific UUID
        current_addresses = self._async_current_ids()
        for discovery_info in bluetooth.async_discovered_service_info(self.hass):
            # Debug: Log ALL discovered devices to help identify the Surplife device
            _LOGGER.debug(
                "Discovered BLE device: name=%s, address=%s, service_uuids=%s, manufacturer_data=%s",
                discovery_info.name,
                discovery_info.address,
                discovery_info.service_uuids,
                discovery_info.manufacturer_data,
            )

            # Case-insensitive UUID matching
            service_uuids_lower = [
                uuid.lower() for uuid in discovery_info.service_uuids
            ]
            if (
                SERVICE_UUID.lower() in service_uuids_lower
                and discovery_info.address not in current_addresses
            ):
                _LOGGER.debug("Found matching Surplife device: %s", discovery_info.name)
                self._discovered_devices[discovery_info.address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("address"): vol.In(
                        {
                            address: f"{info.name} ({address})"
                            for address, info in self._discovered_devices.items()
                        }
                    )
                }
            ),
            errors=errors,
        )
