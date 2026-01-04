# Surplife BLE Simple

A custom Home Assistant integration for Surplife BLE lights.

## Features
- **Local Control**: Works directly via Bluetooth Low Energy (BLE).
- **Discovery**: Automatically discovers compatible devices.
- **Control**: Supports On/Off and RGB color control.

## Installation

### HACS (Recommended)
1. Add this repository to HACS as a custom repository.
2. Search for "Surplife BLE Simple" and install.
3. Restart Home Assistant.

### Manual
1. Copy the `custom_components/surplife_ble_simple` directory to your Home Assistant `custom_components` folder.
2. Restart Home Assistant.

## Configuration
1. Go to **Settings > Devices & Services**.
2. Click **Add Integration** and search for "Surplife BLE Simple".
3. Wait for the scan to complete and select your device from the list.

## Supported Hardware
This integration supports devices advertising the Service UUID `0000e04c-0000-1000-8000-00805f9b34fb`.

## Troubleshooting
- Ensure your Home Assistant host has a working Bluetooth adapter.
- Ensure the device is within range.
- If the device is not found, try power cycling the light.
