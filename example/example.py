import time

import machine
import network
import ubinascii

import mqtt_secrets
import wifi_secrets


PIN_BOARD_LED = "P13_7"

WIFI_CONNECT_TIMEOUT_MS = 15000
MQTT_KEEPALIVE_SECONDS = 60
DIAGNOSTICS_INTERVAL_MS = 30000
MAIN_LOOP_SLEEP_MS = 100

# A watchdog can recover from rare deadlocks, but it can also hide repeated
# crashes as boot loops while debugging. Enable it only after the device is stable.
ENABLE_WATCHDOG = False
WATCHDOG_TIMEOUT_MS = 60000


def sleep_ms(ms):
    try:
        time.sleep_ms(ms)
    except AttributeError:
        time.sleep(ms / 1000)


def print_exception(exc):
    try:
        import sys
        sys.print_exception(exc)
    except Exception:
        print("Exception: %r" % (exc,))


### DOWNLOAD DEPENDENCIES ###
import mip

try:
    from umqtt.simple import MQTTClient
except ImportError:
    print("Exception: umqtt.simple not found. Trying to download...")
    mip.install("umqtt.simple")
    from umqtt.simple import MQTTClient

try:
    import uhome
except ImportError:
    print("Exception: uhome not found. Trying to download...")
    mip.install("github:ederjc/uhome/uhome/uhome.py")
    import uhome


### WIFI SETUP ###
sta = network.WLAN(network.STA_IF)


def feed_watchdog():
    if wdt:
        wdt.feed()


def connect_wifi(timeout_ms=WIFI_CONNECT_TIMEOUT_MS):
    """
    Connect or reconnect Wi-Fi with a bounded wait.

    MQTT reconnects are handled by device.loop(); this function only restores
    the link so the next scheduled MQTT reconnect attempt can succeed.
    """
    if sta.isconnected():
        return True

    sta.active(True)
    sta.connect(wifi_secrets.ssid, wifi_secrets.psk)
    deadline = uhome.ticks_add(uhome.ticks_ms(), timeout_ms)

    while not sta.isconnected():
        feed_watchdog()
        if uhome.ticks_diff(uhome.ticks_ms(), deadline) >= 0:
            print("Wi-Fi connect timed out")
            return False
        sleep_ms(200)

    print("Wi-Fi connected:", sta.ifconfig()[0])
    return True


### DEVICE SETUP ###
device = uhome.Device("Device Name", connect_timeout=10)

# Use umqtt.simple. uhome configures the MQTT callback, retained availability,
# and LWT when device.connect(mqttc) is called.
mqttc = MQTTClient(
    device.id,
    mqtt_secrets.broker,
    port=mqtt_secrets.port,
    user=mqtt_secrets.user,
    password=mqtt_secrets.password,
    keepalive=MQTT_KEEPALIVE_SECONDS,
)

wdt = machine.WDT(timeout=WATCHDOG_TIMEOUT_MS) if ENABLE_WATCHDOG else None


### HELPER FUNCTIONS ###
board_led = machine.Pin(PIN_BOARD_LED, machine.Pin.OUT, value=1)


def identify_board(msg):
    board_led.value(0)
    sleep_ms(1000)
    board_led.value(1)


def reset_for_update(msg):
    machine.soft_reset()


def safe_wifi_value(getter, default="unknown"):
    try:
        return getter()
    except Exception:
        return default


### CREATE ENTITIES ###
identify_button = uhome.Button(device, "Identify", entity_category="config")
identify_button.set_action(identify_board)

fw_update_button = uhome.Button(device, "Update Firmware", entity_category="config")
fw_update_button.set_action(reset_for_update)

signal_strength = uhome.Sensor(
    device,
    "Signal Strength",
    device_class="signal_strength",
    unit_of_measurement="dBm",
    entity_category="diagnostic",
)
wifi_ch = uhome.Sensor(device, "WiFi Channel", device_class="enum", entity_category="diagnostic")
cpu_freq = uhome.Sensor(
    device,
    "CPU Frequency",
    device_class="frequency",
    unit_of_measurement="MHz",
    entity_category="diagnostic",
)
reset_cause = uhome.Sensor(device, "Last Reset Cause", device_class="enum", entity_category="diagnostic")
wifi_mac = uhome.Sensor(device, "WiFi MAC Address", device_class="enum", entity_category="diagnostic")


def publish_static_diagnostics():
    cpu_freq.publish("%.0f" % (machine.freq() / 1000000))
    reset_cause.publish("%s" % machine.reset_cause())
    wifi_mac.publish(
        safe_wifi_value(lambda: ubinascii.hexlify(sta.config("mac"), ":").decode().upper())
    )


def publish_variable_diagnostics():
    signal_strength.publish("%s" % safe_wifi_value(lambda: "%.0f" % sta.status("rssi")))
    wifi_ch.publish("%s" % safe_wifi_value(lambda: sta.config("channel")))


### INITIAL CONNECTION ###
connect_wifi()
device.connect(mqttc)

# These calls also cache values inside the entities. If MQTT is currently
# offline, uhome will force-publish the cached states after a later reconnect.
publish_static_diagnostics()
publish_variable_diagnostics()

next_diagnostics = uhome.ticks_add(uhome.ticks_ms(), DIAGNOSTICS_INTERVAL_MS)


### MAIN LOOP ###
while True:
    try:
        if not sta.isconnected():
            connect_wifi()

        mqtt_connected = device.loop()
        now = uhome.ticks_ms()

        if uhome.ticks_diff(now, next_diagnostics) >= 0:
            next_diagnostics = uhome.ticks_add(now, DIAGNOSTICS_INTERVAL_MS)
            if sta.isconnected() and mqtt_connected:
                publish_variable_diagnostics()

        feed_watchdog()
        sleep_ms(MAIN_LOOP_SLEEP_MS)
    except Exception as exc:
        print_exception(exc)
        feed_watchdog()
        sleep_ms(1000)
