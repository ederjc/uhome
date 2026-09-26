[![License](https://img.shields.io/github/license/ederjc/uhome?style=plastic)](LICENSE.md)
[![Commit activity](https://img.shields.io/github/commit-activity/w/ederjc/uhome?style=plastic)](https://github.com/ederjc/uhome/commits)
[![Issues](https://img.shields.io/github/issues/ederjc/uhome?style=plastic)](https://github.com/ederjc/uhome/issues)
[![Pull requests](https://img.shields.io/github/issues-pr-raw/ederjc/uhome?style=plastic)](https://github.com/ederjc/uhome/pulls)

# uhome
<!-- CI badges -->
[![CPython tests](https://github.com/ederjc/uhome/actions/workflows/test-cpython.yml/badge.svg)](https://github.com/ederjc/uhome/actions/workflows/test-cpython.yml)
[![mpy-cross](https://github.com/ederjc/uhome/actions/workflows/mpy-cross.yml/badge.svg)](https://github.com/ederjc/uhome/actions/workflows/mpy-cross.yml)
[![lint](https://github.com/ederjc/uhome/actions/workflows/lint.yml/badge.svg)](https://github.com/ederjc/uhome/actions/workflows/lint.yml)
![coverage](https://raw.githubusercontent.com/ederjc/uhome/master/coverage.svg)
[![MicroPython tests](https://github.com/ederjc/uhome/actions/workflows/test-micropython.yml/badge.svg)](https://github.com/ederjc/uhome/actions/workflows/test-micropython.yml)
[![MQTT integration](https://github.com/ederjc/uhome/actions/workflows/integration.yml/badge.svg)](https://github.com/ederjc/uhome/actions/workflows/integration.yml)

A MicroPython module for simplified Home Assistant MQTT Auto Discovery.

> [!NOTE]  
> This project is work in progress and not covering all Home Assistant [MQTT entity types](https://www.home-assistant.io/integrations/#search/mqtt), yet. If you are missing an entity type feel free to [contribute](https://github.com/ederjc/uhome/fork) or [open an issue](https://github.com/ederjc/uhome/issues).

## Overview

Home Assistant Auto Discovery is a great and powerful feature, but hard to set up the first time(s). The uhome module is providing a simple and object-oriented interface to set up Auto Discovery for devices & entities in Home Assistant. You can use it for example to bring your custom MicroPython-compatible sensor in Home Assistant in a quick & simple, yet powerful & versatile way.

Behind the scenes, the module wraps the handling of `.json` configuration messages, hides redundancies and allows simple creation of devices and entities which can be auto-discovered by Home Assistant.

## Dependencies

This module needs an MQTT client object from the [umqtt.simple module](https://github.com/micropython/micropython-lib/tree/master/micropython/umqtt.simple/umqtt) for MicroPython. uhome manages reconnects, subscriptions, and availability itself, so `umqtt.simple` is recommended over `umqtt.robust` for new projects.
It can be installed in MicroPython as follows:

```
import mip
mip.install('umqtt.simple')
import umqtt.simple
```

## Installation in MicroPython
The module can be installed using `mip` with these commands:
```
import mip
mip.install('github:ederjc/uhome/uhome/uhome.py')
```

## Usage in MicroPython

The `example/example.py` file is the recommended starting point for resilient devices. In short:

1. Connect Wi-Fi with a bounded timeout and retry Wi-Fi when `sta.isconnected()` becomes false.
2. Use `umqtt.simple.MQTTClient` with a non-zero `keepalive`; do not use `umqtt.robust`, because its reconnect loop can block while uhome is also managing reconnects.
3. Pass the MQTT client to `device.connect(mqttc)`. uhome configures the MQTT callback, retained availability, and last will message there.
4. Register entities, then call `device.loop()` frequently from the main loop. `device.loop()` reconnects MQTT with backoff, restores subscriptions, re-sends discovery, and re-publishes cached states.
5. Do all MQTT publishes in the main loop. Do not publish from `machine.Timer` IRQ callbacks; MQTT socket I/O is not IRQ-safe.
6. Keep the main loop alive with `try`/`except`. If you enable `machine.WDT`, feed it deliberately and only after considering that watchdog resets can hide boot loops during debugging.

Minimal pattern:

```
import network
import time
from umqtt.simple import MQTTClient
import uhome

import mqtt_secrets
import wifi_secrets

sta = network.WLAN(network.STA_IF)
sta.active(True)

def sleep_ms(ms):
    try:
        time.sleep_ms(ms)
    except AttributeError:
        time.sleep(ms / 1000)

def connect_wifi(timeout_ms=15000):
    if sta.isconnected():
        return True
    sta.connect(wifi_secrets.ssid, wifi_secrets.psk)
    deadline = uhome.ticks_add(uhome.ticks_ms(), timeout_ms)
    while not sta.isconnected():
        if uhome.ticks_diff(uhome.ticks_ms(), deadline) >= 0:
            return False
        sleep_ms(200)
    return True

device = uhome.Device("Device Name", connect_timeout=10)
mqttc = MQTTClient(
    device.id,
    mqtt_secrets.broker,
    port=mqtt_secrets.port,
    user=mqtt_secrets.user,
    password=mqtt_secrets.password,
    keepalive=60,
)

signal_strength = uhome.Sensor(
    device,
    "Signal Strength",
    device_class="signal_strength",
    unit_of_measurement="dBm",
    entity_category="diagnostic",
)

connect_wifi()
device.connect(mqttc)

next_publish = uhome.ticks_ms()
while True:
    try:
        if not sta.isconnected():
            connect_wifi()

        mqtt_connected = device.loop()
        now = uhome.ticks_ms()
        if mqtt_connected and sta.isconnected() and uhome.ticks_diff(now, next_publish) >= 0:
            next_publish = uhome.ticks_add(now, 30000)
            signal_strength.publish("%.0f" % sta.status("rssi"))
    except Exception as exc:
        print("main loop exception:", exc)
        sleep_ms(1000)
```

Entity `publish()` calls cache the last payload. If MQTT is disconnected, the state is republished automatically after `device.loop()` reconnects.

## Reconnect and availability behavior

uhome publishes a retained `online` message to the device availability topic after every successful connection and configures an `offline` retained last will. After reconnects it restores all subscriptions, re-sends discovery messages, and force re-publishes cached entity states so Home Assistant does not leave entities `unavailable` or `unknown`. The `online` message is published last, once subscriptions are restored, so commands Home Assistant sends as soon as the device becomes available are not lost.

Call `device.loop()` frequently from the main loop. Do not call it from timer IRQs: MQTT socket I/O, callbacks, discovery publishing, and reconnects are not IRQ-safe.

When Home Assistant publishes its birth message (`online` on `homeassistant/status`), uhome re-sends discovery and re-publishes cached states because Home Assistant may have forgotten non-retained state after restart.

## Supported entities

- Sensor
- Binary Sensor
- Button
- Number
- Select
- Text
- Scene
- Siren
- Switch
- Light
- Lock
- Fan
- Water Heater
- Alarm Control Panel
- Lawn Mower
- Vacuum
- Cover


## MQTT Select entity

Use `Select` when Home Assistant should choose one option from a fixed list and the device should publish the current option back.

```
mode = uhome.Select(device, 'Mode', ['off', 'eco', 'boost'])
mode.set_action(lambda value: apply_mode(value))
mode.publish('eco')
```

### Number

`uhome.Number` exposes writable numeric values such as thresholds, set points, or calibration values via the Home Assistant MQTT Number platform. State and commands use separate MQTT topics: publish the current value with `publish()`, and receive requested changes by registering a callback with `set_action()`.

```
target_level = uhome.Number(device, "Target Level", min=0, max=100, step=5)

def set_target_level(payload):
    # Payload has already been parsed and checked against min/max/step.
    target_level.publish(payload)

target_level.set_action(set_target_level)
target_level.publish(50)
```

## MQTT Text entity

Use `Text` when Home Assistant should send an editable string to the device and the device should publish the current string back.

```
message = uhome.Text(device, 'Display Message', mode='text', max=40)
message.set_action(lambda value: update_display(value))
message.publish('Ready')
```

## MQTT Scene entity

Use `Scene` when Home Assistant should trigger a device-side scene or preset. MQTT scenes are command-only; Home Assistant sends the activation payload to the command topic.

```
night = uhome.Scene(device, 'Night Mode', payload_on='ACTIVATE')
night.set_action(lambda payload: apply_night_mode())
```

## MQTT Siren entity

Use `Siren` when Home Assistant should command an alarm output and the device should publish the current siren state back.

```
alarm = uhome.Siren(device, 'Alarm Siren')
alarm.set_action(lambda payload: set_siren(payload == 'ON'))
alarm.publish('OFF')
```

### Switch

Use `Switch` for controllable on/off outputs such as relays. State and command
messages use separate topics and default to Home Assistant's `ON` / `OFF` payloads.

```
relay = uhome.Switch(device, 'Relay')
relay.set_action(lambda msg: relay.publish(msg == 'ON'))
relay.publish(False)
```

### Light

Use `Light` for MQTT-controlled lamps. It uses Home Assistant's JSON schema with
on/off and brightness support by default, and optional color temperature and RGB
features when requested.

```
lamp = uhome.Light(device, 'Desk Lamp', color_temp=True, rgb=True)
lamp.set_action(lambda cmd: lamp.publish(cmd.get('state', 'OFF'), brightness=cmd.get('brightness')))
lamp.publish('ON', brightness=128, color_temp=300)
```

### Lock

Use `Lock` for MQTT-controlled locks. State and command messages use separate
topics with default `LOCK` / `UNLOCK` commands and `LOCKED` / `UNLOCKED` states.

```
door = uhome.Lock(device, 'Front Door')
door.set_action(lambda msg: door.publish(msg == 'LOCK'))
door.publish(False)
```

### Fan

Use `Fan` for MQTT-controlled fans. On/off state is always enabled. Percentage,
preset modes, oscillation, and direction can be enabled per entity when the device
supports them.

```
fan = uhome.Fan(device, 'Ceiling Fan', percentage=True,
                preset_modes=['auto', 'sleep'], oscillation=True, direction=True)
fan.set_action(lambda feature, msg: print(feature, msg))
fan.publish(True)
fan.publish_percentage(50)
```

### Water Heater

`WaterHeater` exposes a Home Assistant MQTT water heater with separate topics for mode, target temperature, and current temperature.

```python
heater = uhome.WaterHeater(device, 'Boiler', modes=['off', 'eco', 'performance'], min_temp=40, max_temp=65)
heater.set_mode_action(lambda mode: apply_mode(mode))
heater.set_temperature_action(lambda value: apply_target_temperature(float(value)))
heater.publish_mode('eco')
heater.publish_target_temperature(55)
heater.publish_current_temperature(48)
```

### Alarm Control Panel

`AlarmControlPanel` exposes a Home Assistant MQTT alarm control panel with one state topic and one command topic.

```python
alarm = uhome.AlarmControlPanel(device, 'Alarm', code_arm_required=False)
alarm.set_action(lambda payload: handle_alarm_command(payload))
alarm.publish('armed_away')
```

### Lawn Mower

`LawnMower` exposes a Home Assistant MQTT lawn mower with activity state plus start mowing, pause, and dock commands.

```python
mower = uhome.LawnMower(device, 'Garden Mower')
mower.set_start_mowing_action(lambda payload: start_mowing())
mower.set_pause_action(lambda payload: pause_mowing())
mower.set_dock_action(lambda payload: return_to_dock())
mower.publish_activity('mowing')
```

### Vacuum

`Vacuum` exposes a Home Assistant MQTT vacuum using the current `state` schema. It publishes a JSON state payload and supports standard command, fan speed, custom command, and clean-segments command topics.

```python
vacuum = uhome.Vacuum(device, 'Robot Vacuum', fanspd_lst=['quiet', 'max'])
vacuum.set_command_action(lambda command: handle_vacuum_command(command))
vacuum.set_fan_speed_action(lambda speed: set_fan_speed(speed))
vacuum.publish_state('cleaning', battery_level=82, fan_speed='quiet')
```

## Cover entity

Use `Cover` for MQTT covers such as garage doors, blinds, or shades. It exposes open, close, and stop commands, plus optional current and set-position topics when `position=True`.

```
cover = uhome.Cover(device, 'Garage Door', position=True)
cover.set_action(open_cb, close_cb, stop_cb, set_position_cb)
cover.publish('closed')
cover.publish_position(0)
```

## Testing

Desktop tests can be run from the repository root with:

```
python -m unittest discover -s tests -v
```

GitHub Actions also builds the pinned MicroPython unix port and runs the same
`tests/test_*.py` files under MicroPython using `mip`-installed
`unittest-discover`.

To run the broker-backed integration test locally, start a Mosquitto 2.x broker with the
test config (Mosquitto 2.x only accepts remote/anonymous clients when a listener is
configured explicitly) and point the test at it:

```
python -m pip install -r requirements-dev.txt
docker run --rm -d --name uhome-mosquitto -p 1883:1883 -v "$PWD/tests/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" eclipse-mosquitto:2.1-alpine
UHOME_REQUIRE_REAL_BROKER=1 python -m unittest discover -s tests -p test_integration.py -v
docker stop uhome-mosquitto
```

## More Information
### Home Assistant
- [MQTT integration](https://www.home-assistant.io/integrations/mqtt)
- [MQTT Sensor integration](https://www.home-assistant.io/integrations/sensor.mqtt)
- [MQTT Binary Sensor integration](https://www.home-assistant.io/integrations/binary_sensor.mqtt)
- [MQTT Number integration](https://www.home-assistant.io/integrations/number.mqtt)
