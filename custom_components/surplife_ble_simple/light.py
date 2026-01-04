"""Surplife BLE Simple Light Platform."""
from __future__ import annotations

import logging
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components.light import (
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

DOMAIN = "surplife_ble_simple"
SERVICE_UUID = "0000e04c-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000a04c-0000-1000-8000-00805f9b34fb"

# Packet Constants
CMD_ON = [0xA0, 0x11, 0x04, 0x01, 0xB1, 0x21]
CMD_OFF = [0xA0, 0x11, 0x04, 0x00, 0x70, 0xE1]
HEADER_RGB = [0xA0, 0x04, 0x1A]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Light platform."""
    address = config_entry.data["address"]
    ble_device = bluetooth.async_ble_device_from_address(hass, address)
    if not ble_device:
        _LOGGER.error("Device not found at address %s", address)
        return

    async_add_entities([SurplifeBLELight(ble_device, config_entry.title)])


class SurplifeBLELight(LightEntity):
    """Surplife BLE Light Entity."""

    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF # Default, upgrades to RGB when used

    def __init__(
        self,
        ble_device: bluetooth.BluetoothServiceInfoBleak,
        name: str,
    ) -> None:
        """Initialize the light."""
        self._ble_device = ble_device
        self._attr_name = name
        self._attr_unique_id = ble_device.address
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ble_device.address)},
            name=name,
            manufacturer="Surplife",
        )
        self._is_on = False
        self._rgb_color = (255, 255, 255)
        self._client: BleakClient | None = None

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._is_on

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value."""
        return self._rgb_color

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_RGB_COLOR in kwargs:
            rgb = kwargs[ATTR_RGB_COLOR]
            self._rgb_color = rgb
            self._attr_color_mode = ColorMode.RGB
            await self._send_rgb_command(rgb)
        else:
            self._attr_color_mode = ColorMode.ONOFF
            await self._send_command_raw(CMD_ON)
        
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._send_command_raw(CMD_OFF)
        self._is_on = False
        self.async_write_ha_state()

    def _calculate_checksum(self, packet: list[int]) -> int:
        """Calculate checksum: Sum of bytes masked to 0xFF."""
        return sum(packet) & 0xFF

    async def _send_rgb_command(self, rgb: tuple[int, int, int]) -> None:
        """Send RGB command."""
        # Generic RGB packet structure:
        # Header: [0xA0, 0x04, 0x1A]
        # Payload: [Red, Green, Blue, 0x00, 0x00, 0x00, 0x00, 0x00] (8 bytes)
        # Checksum: Calculate sum of Header + Payload.
        r, g, b = rgb
        packet = HEADER_RGB + [r, g, b, 0x00, 0x00, 0x00, 0x00, 0x00]
        checksum = self._calculate_checksum(packet)
        packet.append(checksum)
        await self._send_command_raw(packet)

    async def _send_command_raw(self, packet: list[int]) -> None:
        """Send raw command to device."""
        # We need to re-fetch the device object to ensure it's fresh for the connection
        # But for now, we rely on the one passed or try to get a client.
        # Home Assistant recommends using `bleak_retry_connector` or getting a client via helper.
        # Since I didn't verify if `bleak_retry_connector` is available in the user's env (it should be standard in HA),
        # I'll use the basic `BleakClient` dealing with the address, but getting the device from HA is safer.
        
        # NOTE: In a real HA integration, we should use `async_ble_device_from_address` inside the call 
        # to ensure we have the latest BLEDevice object if it rotates.
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self._attr_unique_id)
        if not ble_device:
            _LOGGER.error("Device %s not found", self._attr_unique_id)
            return

        try:
            async with BleakClient(ble_device) as client:
                await client.write_gatt_char(WRITE_UUID, bytearray(packet), response=True)
        except BleakError as e:
            _LOGGER.error("Failed to send command to %s: %s", self._attr_unique_id, e)
