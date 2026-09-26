import time

import machine
import mqtt_secrets
import network
import ubinascii
import wifi_secrets

PIN_BOARD_LED = 'P13_7'

### CONNECT TO WIFI ###
sta = network.WLAN(network.STA_IF)
sta.connect(wifi_secrets.ssid, wifi_secrets.psk)

### DOWNLOAD DEPENDENCIES ###
import mip

try:
    import umqtt.robust
except:
    print("Exception: umqtt.robust not found. Trying to download...")
    mip.install('umqtt.simple')
    mip.install('umqtt.robust')
    import umqtt.robust

try:
    import uhome
except:
    print("Exception: uhome not found. Trying to download...")
    mip.install('github:ederjc/uhome/uhome/uhome.py')
    import uhome

### DEVICE SETUP ###
"""
This is an example of a simple device setup. It creates
a device which we can later use to assign entities to.
"""
device = uhome.Device('Device Name')
mqttc = umqtt.robust.MQTTClient(device.id, mqtt_secrets.broker, user=mqtt_secrets.user, password=mqtt_secrets.password, keepalive=60)
device.connect(mqttc)

### HELPER FUNCTIONS ###
board_led = machine.Pin(PIN_BOARD_LED, machine.Pin.OUT, value=1)


def identify_board(msg):
    """
    This function is called when the identify_button is pressed.
    It will toggle the board's LED to indicate the board's location.
    """
    board_led.value(0)
    time.sleep(1)
    board_led.value(1)


### CREATE ENTITIES ###
"""
These are some default entities that are useful for diagnostics.
"""
identify_button = uhome.Button(device, 'Identify', entity_category="config")  # Create a button to identify the board.
identify_button.set_action(identify_board)  # Set the action to the identify_board function.

fw_update_button = uhome.Button(device, 'Update Firmware', entity_category="config")  # Create a button to trigger a firmware update.
fw_update_button.set_action(lambda x: machine.soft_reset())  # Set the action to the update firmware function.

signal_strength = uhome.Sensor(device, 'Signal Strength', device_class="signal_strength", unit_of_measurement='dBm', entity_category="diagnostic")
wifi_ch = uhome.Sensor(device, 'WiFi Channel', device_class="enum", entity_category="diagnostic")
cpu_freq = uhome.Sensor(device, 'CPU Frequency', device_class="frequency", unit_of_measurement='MHz', entity_category="diagnostic")
reset_cause = uhome.Sensor(device, 'Last Reset Cause', device_class="enum", entity_category="diagnostic")
wifi_mac = uhome.Sensor(device, 'WiFi MAC Address', device_class="enum", entity_category="diagnostic")

"""
The uhome module keeps track of all entities.
With this method we can send the discovery
message for all entities to Home Assistant:
"""
device.discover_all()
"""
The discover message needs to be sent before
any values are published to Home Assistant.
It is recommended to run this method regularly
while the device is running to ensure that
all entities are up to date in Home Assistant.
"""

### PUBLISH ENTITY VALUES ###
"""
Here we publish the values of the diagnostic entities.
Some of these values are published only once, while others
should be published regularly to keep Home Assistant up to date.
"""
cpu_freq.publish(f'{machine.freq() / 1e6:.0f}')
reset_cause.publish(f'{machine.reset_cause()}')
wifi_mac.publish(ubinascii.hexlify(sta.config("mac"), ":").decode().upper())


def publishDiagnostics(tmr=None):
    """
    Helper function to publish variable diagnostic values.
    """
    signal_strength.publish(f'{sta.status('rssi'):.0f}')
    wifi_ch.publish(f'{sta.config('channel')}')


### INTERRUPTS FOR PUBLISHING ###
"""
These interrupts are taking care of publishing the updated
values to Home Assistant, either periodically or when a.
certain event (like a pin level change) occurs.
"""
diagnostics_tmr = machine.Timer(0, mode=machine.Timer.PERIODIC, period=30000, callback=publishDiagnostics)

while True:
    if not sta.isconnected():
        sta = sta.connect(wifi_secrets.ssid, wifi_secrets.psk)  # Reconnect to WiFi if connection is lost.

    device.loop()  # Handle all device specific tasks (mandatory).
