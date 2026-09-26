[![License](https://img.shields.io/github/license/ederjc/uhome?style=plastic)](LICENSE.md)
[![Commit activity](https://img.shields.io/github/commit-activity/w/ederjc/uhome?style=plastic)](https://github.com/ederjc/uhome/commits)
[![Issues](https://img.shields.io/github/issues/ederjc/uhome?style=plastic)](https://github.com/ederjc/uhome/issues)
[![Pull requests](https://img.shields.io/github/issues-pr-raw/ederjc/uhome?style=plastic)](https://github.com/ederjc/uhome/pulls)

# uhome
<!-- CI badges -->
[![CPython tests](https://github.com/ederjc/uhome/actions/workflows/test-cpython.yml/badge.svg)](https://github.com/ederjc/uhome/actions/workflows/test-cpython.yml)

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

1. Setup a device:
```
import uhome
device = uhome.Device('Device Name')
```
At least one device is required as foundation to create entities.

2. Create a MQTT client object:
```
mqttc = umqtt.simple.MQTTClient(device.id, <your mqtt broker address>, keepalive=60)
```
A MQTT client object is required to handle communication. Make sure to set a decent `keepalive` value in order to make the availability feature of the uhome module work properly. MQTT client IDs must be unique per physical device; reusing a client ID causes broker session takeover and flapping availability.

3. Let the device know that it should use the mqttc object to communicate:
```
device.connect(mqttc)
```
If the first broker connection fails, `connect()` returns `False` and `device.loop()` will retry with backoff. The method keeps the existing public API and can be called before or after entities are created.

4. Create an entity:
```
signal_strength = uhome.Sensor(device, 'Signal Strength', device_class="signal_strength", unit_of_measurement='dBm', entity_category="diagnostic")
```
For demonstration we are using the Wi-Fi signal strength which can be aquired from the network API on MicroPython devices, so no external sensor is required.
This will be a continual value, therefore we use the `uhome.Sensor()` class for creating a MQTT Sensor. If it would be a binary sensor like a window contact we would use `uhome.BinarySensor()`.
The first argument is the device this entity will be assigned to, the second argument is the name of the entity. This name will also be used to derive the unique identifier. All other arguments are passed as keyword arguments directly into the Auto Discovery configuration. You can read up their meaning on the respective Home Assistant docs page, e.g. for [here](https://www.home-assistant.io/integrations/sensor.mqtt) for MQTT Sensor entities.

5. Discover
Now the configuration of the entity can be sent to Home Assistant, the entity can be "auto-discovered":
```
device.discover_all()
```
Note that I am using `device.discover_all()` here instead of `signal_strength.discover()`. This simplifies the process if you have created multiple entities. One call of `device.discover_all()` will report all entities assigned to `device` to Home Assistant.

6. Publish
The device and entity will now appear in Home Assistant (under *Settings -> Integrations -> MQTT*). The value will show as unknown, because we did not publish any value to our signal strength entity, yet.
We can do this using this command:
```
signal_strength.publish("%.0f" % sta.status('rssi'))
```
In this case `sta` is the network object used to connect to the Wi-Fi network. Have a look [here](https://github.com/ederjc/uhome/blob/master/example/example.py) for details.
`sta.status('rssi')` gives the signal strength in dBm and the `:.0f` cuts all decimals.

## Reconnect and availability behavior

uhome publishes a retained `online` message to the device availability topic after every successful connection and configures an `offline` retained last will. After reconnects it restores all subscriptions, re-sends discovery messages, and force re-publishes cached entity states so Home Assistant does not leave entities `unavailable` or `unknown`.

Call `device.loop()` frequently from the main loop. Do not call it from timer IRQs: MQTT socket I/O, callbacks, discovery publishing, and reconnects are not IRQ-safe.

When Home Assistant publishes its birth message (`online` on `homeassistant/status`), uhome re-sends discovery and re-publishes cached states because Home Assistant may have forgotten non-retained state after restart.

## Supported entities

- Sensor
- Binary Sensor
- Button
- Number

## Testing

Desktop tests can be run from the repository root with:

```
python -m unittest discover -s tests -v
```

## More Information
### Home Assistant
- [MQTT integration](https://www.home-assistant.io/integrations/mqtt)
- [MQTT Sensor integration](https://www.home-assistant.io/integrations/sensor.mqtt)
- [MQTT Binary Sensor integration](https://www.home-assistant.io/integrations/binary_sensor.mqtt)