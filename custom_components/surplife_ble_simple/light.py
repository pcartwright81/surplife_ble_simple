"""Surplife BLE Simple Light Platform with Status Monitoring."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.components.light import (
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CMD_OFF,
    CMD_ON,
    DOMAIN,
    HEADER_RGB,
    NOTIFY_UUID,
    POKE_COMMAND,
    WRITE_UUID,
)

_LOGGER = logging.getLogger(__name__)

# Reconnection delay in seconds
RECONNECT_DELAY = 5.0


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
    """Surplife BLE Light Entity with persistent connection and status monitoring."""

    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(
        self,
        ble_device: BLEDevice,
        name: str,
    ) -> None:
        """Initialize the light."""
        self._ble_device = ble_device
        self._address = ble_device.address
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
        self._reconnect_task: asyncio.Task | None = None
        self._connect_task: asyncio.Task | None = None
        self._shutting_down = False

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return self._client is None or not self._client.is_connected

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._is_on

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return the rgb color value."""
        return self._rgb_color

    async def async_added_to_hass(self) -> None:
        """Run when entity is added to hass."""
        await super().async_added_to_hass()
        # Start the connection in the background (don't block)
        self._connect_task = self.hass.async_create_task(self._async_connect())

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity is being removed from hass."""
        self._shutting_down = True
        # Cancel any pending reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        # Disconnect the client
        await self._async_disconnect()
        await super().async_will_remove_from_hass()

    async def _async_connect(self) -> None:
        """Establish connection and subscribe to notifications."""
        if self._shutting_down:
            return

        # Get the latest BLE device reference
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self._address)
        if not ble_device:
            _LOGGER.warning("Device %s not found, scheduling reconnect", self._address)
            self._schedule_reconnect()
            return

        try:
            _LOGGER.debug("Connecting to %s", self._address)
            self._client = await establish_connection(
                BleakClient,
                ble_device,
                self._address,
                disconnected_callback=self._on_disconnect,
            )
            _LOGGER.info("Connected to %s", self._address)

            # Subscribe to notifications
            await self._client.start_notify(NOTIFY_UUID, self._handle_notification)
            _LOGGER.debug("Subscribed to notifications on %s", NOTIFY_UUID)

            # Send poke command to get initial state
            await self._client.write_gatt_char(
                WRITE_UUID, bytearray(POKE_COMMAND), response=True
            )
            _LOGGER.debug("Sent poke command to get initial state")

            # Update availability
            self.async_write_ha_state()

        except BleakError as e:
            _LOGGER.error("Failed to connect to %s: %s", self._address, e)
            self._client = None
            self._schedule_reconnect()

    async def _async_disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(NOTIFY_UUID)
            except BleakError:
                pass  # Ignore errors when stopping notifications
            try:
                await self._client.disconnect()
            except BleakError:
                pass  # Ignore disconnect errors
        self._client = None
        self.async_write_ha_state()

    @callback
    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection callback."""
        _LOGGER.warning("Disconnected from %s", self._address)
        self._client = None
        self.async_write_ha_state()
        if not self._shutting_down:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnection attempt."""
        if self._shutting_down:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Already scheduled

        async def reconnect() -> None:
            await asyncio.sleep(RECONNECT_DELAY)
            if not self._shutting_down:
                await self._async_connect()

        self._reconnect_task = self.hass.async_create_task(reconnect())
        _LOGGER.debug("Scheduled reconnect in %s seconds", RECONNECT_DELAY)

    def _handle_notification(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Received notification: %s", data.hex())

        # Parse status packets starting with 0xA1
        if len(data) >= 4 and data[0] == 0xA1:
            # Check for state packet (data[2] == 0x66 or similar patterns)
            if data[2] == 0x66:
                new_state = data[3] == 0x01
                if self._is_on != new_state:
                    self._is_on = new_state
                    _LOGGER.info(
                        "Device %s state updated: %s",
                        self._address,
                        "ON" if new_state else "OFF",
                    )
                    self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if ATTR_RGB_COLOR in kwargs:
            rgb = kwargs[ATTR_RGB_COLOR]
            self._rgb_color = rgb
            await self._send_rgb_command(rgb)
        else:
            # Turn on with last known color
            await self._send_command_raw(CMD_ON)

        # Note: State will be updated via notification callback
        # Only update optimistically if not connected
        if not self.available:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._send_command_raw(CMD_OFF)

        # Note: State will be updated via notification callback
        # Only update optimistically if not connected
        if not self.available:
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
        """Send raw command to device using persistent connection."""
        if self._client and self._client.is_connected:
            try:
                await self._client.write_gatt_char(
                    WRITE_UUID, bytearray(packet), response=True
                )
                _LOGGER.debug("Sent command: %s", bytes(packet).hex())
            except BleakError as e:
                _LOGGER.error("Failed to send command to %s: %s", self._address, e)
                # Connection may have dropped, trigger reconnect
                self._on_disconnect(self._client)
        else:
            # Not connected, try to connect first then send
            _LOGGER.warning(
                "Not connected to %s, attempting to connect and send", self._address
            )
            await self._async_connect()
            if self._client and self._client.is_connected:
                try:
                    await self._client.write_gatt_char(
                        WRITE_UUID, bytearray(packet), response=True
                    )
                    _LOGGER.debug(
                        "Sent command after reconnect: %s", bytes(packet).hex()
                    )
                except BleakError as e:
                    _LOGGER.error(
                        "Failed to send command to %s after reconnect: %s",
                        self._address,
                        e,
                    )
