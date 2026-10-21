# pypamc_204

[![PyPI](https://img.shields.io/pypi/v/pypamc-204)](https://pypi.org/project/pypamc-204/)
[![Python](https://img.shields.io/pypi/pyversions/pypamc-204)](https://pypi.org/project/pypamc-204/)
[![Tests](https://github.com/mechano-transformer/pypamc-204/actions/workflows/test.yml/badge.svg)](https://github.com/mechano-transformer/pypamc-204/actions/workflows/test.yml)

Python library for the PAMC-204 / PAMC-204A / PAMC-204-RJ piezo-assisted motor controller.

> 日本語版は [README.md](README.md) を参照してください。

- **PyPI:** https://pypi.org/project/pypamc-204/
- **GitHub:** https://github.com/mechano-transformer/pypamc-204

## Installation

```bash
pip install pypamc_204
```

Development (local install):

```bash
cd pypamc-204
pip install -e .
```

## Requirements

- Python 3.9+
- pyserial

## Development setup

### 1. Clone the repository

```bash
git clone https://github.com/mechano-transformer/pypamc-204.git
cd pypamc-204
```

### 2. Create and activate a virtual environment (venv)

**Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install with the development dependencies

```bash
pip install -e ".[dev]"
```

This installs `pypamc204` plus `pytest`.

### 4. Run the unit tests

```bash
pytest
```

Verbose output:

```bash
pytest -v
```

Run a single test class:

```bash
pytest tests/test_controller.py::TestRotation -v
```

### 5. Deactivate the virtual environment

```bash
deactivate
```

## Quick start

```python
from pypamc204 import PAMC204

# Connect to the controller (the port is auto-detected; address 1 is the default)
with PAMC204() as ctrl:
    # Check the firmware version
    print(ctrl.get_firmware_info())

    # Set the output voltage to 100 V
    ctrl.set_voltage(100)

    # Drive CH1 forward (500 Hz, 1000 pulses)
    ctrl.rotate_forward(channel=1, frequency=500, pulses=1000)

    # Drive CH2 in reverse (continuous)
    ctrl.rotate_reverse(channel=2, frequency=300)

    # Stop
    ctrl.stop()
```

## Usage

### Connecting

When the port name is omitted, the serial port is auto-detected by matching
the USB VID/PID (FTDI FT230X: `0403:6015`). The port name can also be
specified explicitly.

```python
from pypamc204 import PAMC204, find_port

# Context manager (recommended), with port auto-detection
with PAMC204(address=1) as ctrl:
    ...

# Specify the port explicitly (skips auto-detection)
with PAMC204("COM3", address=1) as ctrl:
    ...

# Manual connection management
ctrl = PAMC204()
ctrl.open()
print(ctrl.port)  # the port actually in use (e.g. "COM3", "/dev/ttyUSB0")
# ... operations ...
ctrl.close()

# Detection only (raises ConnectionError if none or multiple candidates)
port = find_port()
```

### Specifying the address (E01–E32)

The PAMC-204 / PAMC-204A can be daisy-chained over RS-485, so each driver has a
**unique address in the range E01–E32**. Every command is prefixed with this
address (`Exx`) when sent (e.g. `E01DAC2700`, `E05NR...`).

In this library you **specify the address as the integer `address`**. It is
converted internally to the `E{address:02d}` form (two digits, zero-padded) and
prepended to each command.

| `address` argument | Prefix sent over serial |
|---|---|
| `1` (default) | `E01` |
| `5` | `E05` |
| `32` | `E32` |

```python
# Fix the address at connection time (the most common usage)
with PAMC204("COM3", address=1) as ctrl:   # -> everything is sent as "E01..."
    ctrl.set_voltage(100)                  # sends: E01DAC2700

with PAMC204("COM3", address=5) as ctrl:   # -> everything is sent as "E05..."
    ctrl.set_voltage(100)                  # sends: E05DAC2700
```

- The valid range is **1–32**. Out-of-range values raise `ValueError` (mapping to `E01`–`E32`).
- The default is `1` (`E01`).

#### Handling multiple drivers on the same port

When several drivers share one serial port, either use a separate instance per
address or switch the `address` attribute.

```python
ctrl = PAMC204("COM3")
ctrl.open()

ctrl.address = 1        # subsequent commands target E01
ctrl.set_voltage(100)

ctrl.address = 2        # subsequent commands target E02
ctrl.set_voltage(120)

ctrl.close()
```

`ping()` can check a different address for a single call only (the instance's
`address` is not changed).

```python
with PAMC204("COM3", address=1) as ctrl:
    ctrl.ping(5)        # temporarily check whether E05 responds (sends: E05)
```

### Specifying the channel / axis (CH1–CH4 = A–D)

A single driver can control up to four axes. The **`channel`** argument of every
method accepts either a **number `1`–`4`** or an **axis letter `"A"`–`"D"`**
(upper- or lower-case). They map as follows:

| Number | Axis letter | Axis |
|---|---|---|
| `1` | `"A"` | CH1 |
| `2` | `"B"` | CH2 |
| `3` | `"C"` | CH3 |
| `4` | `"D"` | CH4 |

The axis notation in the command string differs by command family, but the
library converts it automatically — both forms produce the same result.

| Command family | Axis notation | Example (CH1 / CH2) |
|---|---|---|
| Rotation drive (`NR`/`RR`) | trailing `A`–`D` | `E01NR05000100`**`A`** / …**`B`** |
| Position / velocity / status (`PA`/`PR`/`VA`/`DH`/`MD?`/`TP?`, etc.) | `1`–`4` right after the address | `E01`**`1`**`PA5000` / `E01`**`2`**`PA5000` |

```python
with PAMC204("COM3", address=1) as ctrl:
    # A number and an axis letter send the exact same command
    ctrl.rotate_forward(channel=1,   frequency=500, pulses=100)  # sends: E01NR05000100A
    ctrl.rotate_forward(channel="A", frequency=500, pulses=100)  # sends: E01NR05000100A

    ctrl.move_absolute(channel=2,   position=5000)               # sends: E012PA5000
    ctrl.move_absolute(channel="B", position=5000)               # sends: E012PA5000
```

`channel` accepts **only** `1`/`2`/`3`/`4` or `"A"`/`"B"`/`"C"`/`"D"`
(lower-case allowed). Anything else (`0`, `5`, `"1"`, `"E"`, `True`, etc.)
raises `ValueError`.

### About command responses

The PAMC-204 / PAMC-204A has **commands that return a response and commands that do not**,
and this library distinguishes them per method (following the device manual).

- **Returns a response:** `ping()` / `set_address()` / `set_voltage()` /
  `rotate_forward()` / `rotate_reverse()` / `stop()`, and every query command
  ending in `?`.
  → The method returns the response (an `OK` confirmation, the `FIN` pulse
  count, or the queried value). If no response arrives, `TimeoutError` is raised.
- **Returns no response:** `abort()` / `stop_channel()` / `set_home()` /
  `move_absolute()` / `move_relative()` / `move_indefinite()` / `set_velocity()`.
  → These only send; there is no return value (and no `timeout` wait occurs).

### Detecting drivers

```python
with PAMC204("COM3") as ctrl:
    # Check whether a driver exists at a specific address
    if ctrl.ping(1):
        print("E01 is connected")

    # Scan all addresses (1-32)
    found = ctrl.scan_addresses()
    print(f"Found drivers: {found}")
```

### Changing the address

```python
# NOTE: run this only with a single driver connected
with PAMC204("COM3") as ctrl:
    ctrl.set_address(5)  # change the address to E05
```

### Adjusting the output voltage

```python
with PAMC204("COM3") as ctrl:
    # Choose from 70, 80, 90, 100, 110, 120, 130, 140, 150 V
    ctrl.set_voltage(120)

    # Specify the DAC value directly (1900-4095)
    ctrl.set_voltage_raw(3000)
```

### Driving the motor (forward / reverse)

```python
with PAMC204("COM3") as ctrl:
    # Forward: CH1, 1000 Hz, 5000 pulses
    ctrl.rotate_forward(channel=1, frequency=1000, pulses=5000)

    # Reverse: CH2, 500 Hz, continuous (pulses=0)
    ctrl.rotate_reverse(channel=2, frequency=500)

    # Extended pulses (up to 999999)
    ctrl.rotate_forward(channel=1, frequency=800, pulses=100000)

    # Stop continuous drive (the driven pulse count is returned)
    result = ctrl.stop()
    print(result)  # e.g. "E01FIN1456"

    # Get just the pulse count
    count = ctrl.get_stop_pulse_count()
```

### Stopping motion

```python
with PAMC204("COM3") as ctrl:
    # Stop continuous drive (returns the pulse count)
    ctrl.stop()

    # Immediately stop all channels (no response)
    ctrl.abort()

    # Stop a specific channel (no response)
    ctrl.stop_channel(channel=1)
```

### Home position

```python
with PAMC204("COM3") as ctrl:
    # Set the home position
    ctrl.set_home(channel=1, position=1000)

    # Get the home position
    home = ctrl.get_home(channel=1)
    print(f"Home position: {home}")
```

### Position control

```python
with PAMC204("COM3") as ctrl:
    # Set the velocity (1-1500 steps/sec)
    ctrl.set_velocity(channel=1, velocity=500)

    # Move to an absolute position
    ctrl.move_absolute(channel=1, position=5000)

    # Relative move (+1000 steps from the current position)
    ctrl.move_relative(channel=1, steps=1000)

    # Indefinite move
    ctrl.move_indefinite(channel=1, direction="+")

    # Wait until the motion completes
    ctrl.wait_until_done(channel=1, timeout=10.0)
```

### Acceleration (F/W Ver.0.2.1 and later)

Supports `ExxmACnnnn` / `ExxmAC?`. The acceleration is specified in the range
**1–150000 steps/sec²**.

```python
with PAMC204("COM3") as ctrl:
    # Set the acceleration (an axis letter also works)
    ctrl.set_acceleration(channel=1, acceleration=10000)   # sends: E011AC10000
    ctrl.set_acceleration(channel="A", acceleration=10000) # same as above

    # Query the acceleration
    acc = ctrl.get_acceleration(channel=1)                 # sends: E011AC?
    print(f"Acceleration: {acc} steps/sec^2")
```

**Commands affected by the acceleration:** indefinite move (`move_indefinite`) /
absolute move (`move_absolute`) / relative move (`move_relative`) /
channel stop (`stop_channel`).
**Not supported:** pulse drive (`rotate_forward` / `rotate_reverse`) and
continuous-drive stop (`stop`).

> **Note:** This command is available only on PAMC-204 / PAMC-204A firmware **Ver.0.2.1 and
> later**. Out-of-range values (0, 150001, decimals, etc.) or non-integers raise
> `ValueError`.

### Status queries

```python
with PAMC204("COM3") as ctrl:
    # Actual position
    pos = ctrl.get_position(channel=1)

    # Target position (target while driving / actual position while stopped)
    target = ctrl.get_target_position(channel=1)

    # Target position of a relative move
    rel_target = ctrl.get_relative_target(channel=1)

    # Velocity
    vel = ctrl.get_velocity(channel=1)

    # Motion-done check (True = stopped, False = driving)
    done = ctrl.is_motion_done(channel=1)

    # Moving check (True = moving, False = stopped)
    moving = ctrl.is_moving(channel=1)
```

### Drive status, serial number, and FIN transmission

```python
with PAMC204("COM3") as ctrl:
    # Query the drive status (F/W Ver.0.1.7+)
    status = ctrl.get_drive_status()   # "S" (stopped) / "NR1500A" (forward) / "RR1500A" (reverse)
    if ctrl.is_driving():
        print(f"Driving: {status}")

    # Enable/disable the pulse-count transmission on continuous-drive stop (F/W Ver.0.1.8+)
    ctrl.set_txfin(True)               # make stop() return "FIN<pulse count>" (default)
    # ctrl.set_txfin(False)            # NOTE: when OFF, stop() returns nothing -> TimeoutError

    # Get the serial number
    sn = ctrl.get_serial_number()      # e.g. "10001"
```

### Operating on all four channels

Utilities that send a command to CH1–CH4 in sequence (equivalent to the
`*_all_channels` API in libpamc-204 / libpamc-204A). The PAMC-204 / PAMC-204A drives one axis at a time, so
these run sequentially internally as well.

```python
with PAMC204("COM3") as ctrl:
    # Move all channels by the same relative amount
    ctrl.move_relative_all(1000)

    # Move all channels indefinitely in the same direction
    ctrl.move_indefinite_all("+")

    # Stop each channel (ExxmST). Use abort() for an immediate stop of all channels.
    ctrl.stop_all()

    # Read all channels' actual positions / motion-done statuses at once
    positions = ctrl.get_position_all()      # [CH1, CH2, CH3, CH4]
    done = ctrl.get_motion_done_all()        # [True/False, ...]
```

### Sending raw commands

```python
with PAMC204("COM3") as ctrl:
    response = ctrl.send_raw("E01INF")
    print(response)
```

## Command reference

| Method | Command | Description |
|---|---|---|
| `get_firmware_info()` | `INF` [^inf] | Check the firmware version |
| `ping()` | `Exx` | Check whether a driver exists |
| `set_address()` | `SETADDRxx` | Change the address |
| `set_voltage()` | `ExxDACnnnn` | Adjust the output voltage |
| `rotate_forward()` | `ExxNRnnnnyyyyz` | Forward drive |
| `rotate_reverse()` | `ExxRRnnnnyyyyz` | Reverse drive |
| `stop()` | `ExxS` | Stop continuous drive |
| `abort()` | `ExxAB` | Stop motion |
| `set_home()` | `ExxmDHnnnn` | Set the home position |
| `get_home()` | `ExxmDH?` | Query the home position |
| `is_motion_done()` | `ExxmMD?` | Motion-done status |
| `move_indefinite()` | `ExxmMVn` | Indefinite move |
| `is_moving()` | `ExxmMV?` | Query the move direction |
| `move_absolute()` | `ExxmPAnnnn` | Absolute move |
| `get_target_position()` | `ExxmPA?` | Query the target position |
| `move_relative()` | `ExxmPRnnnn` | Relative move |
| `get_relative_target()` | `ExxmPR?` | Query the relative target position |
| `stop_channel()` | `ExxmST` | Stop a channel |
| `get_position()` | `ExxmTP?` | Query the actual position |
| `set_velocity()` | `ExxmVAnnnn` | Set the velocity |
| `get_velocity()` | `ExxmVA?` | Query the velocity |
| `set_acceleration()` | `ExxmACnnnn` | Set the acceleration (F/W Ver.0.2.1+) |
| `get_acceleration()` | `ExxmAC?` | Query the acceleration (F/W Ver.0.2.1+) |
| `get_drive_status()` / `is_driving()` | `ExxST?` | Query the drive status (F/W Ver.0.1.7+) |
| `set_txfin()` | `ExxTXFINn` | Enable/disable pulse-count TX on stop (F/W Ver.0.1.8+) |
| `get_serial_number()` | `ExxSNO?` | Query the serial number |
| `move_relative_all()` | `ExxmPRnnnn` ×4 | Relative move on all channels |
| `move_indefinite_all()` | `ExxmMVn` ×4 | Indefinite move on all channels |
| `stop_all()` | `ExxmST` ×4 | Stop all channels |
| `get_position_all()` | `ExxmTP?` ×4 | Read all channels' actual positions |
| `get_motion_done_all()` | `ExxmMD?` ×4 | Read all channels' motion-done statuses |

[^inf]: The manual lists the syntax as `ExxINF`, but the firmware-version check sends `INF` without an address (matching the `get_firmware_info()` implementation).

## Communication specifications

| Item | Value |
|---|---|
| Baud rate | 115200 bps |
| Data bits | 8 bit |
| Parity | None |
| Stop bits | 1 bit |
| Flow control | None |
| Delimiter | CR + LF |

## License

MIT
