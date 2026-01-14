"""Constants for Surplife BLE Simple integration."""

DOMAIN = "surplife_ble_simple"
SERVICE_UUID = "0000c04c-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000a04c-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000f04c-0000-1000-8000-00805f9b34fb"

# Poke command to trigger status report from device
POKE_COMMAND = [0x77, 0x00, 0x00, 0x03]

# Packet Constants
CMD_ON = [0xA0, 0x11, 0x04, 0x01, 0xB1, 0x21]
CMD_OFF = [0xA0, 0x11, 0x04, 0x00, 0x70, 0xE1]
HEADER_RGB = [0xA0, 0x04, 0x1A]
