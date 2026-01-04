"""Config flow for Surplife BLE Simple integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

domain = "surplife_ble_simple"
SERVICE_UUID = "0000e04c-0000-1000-8000-00805f9b34fb"


class ConfigFlow(config_entries.ConfigFlow, domain=domain):
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
            if (
                SERVICE_UUID in discovery_info.service_uuids
                and discovery_info.address not in current_addresses
            ):
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
