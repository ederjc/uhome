import json
import os
import sys
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

import uhome

IS_CPYTHON = getattr(getattr(sys, "implementation", None), "name", "") == "cpython"
PAHO_IMPORT_ERROR = None
UUID_IMPORT_ERROR = None
mqtt = None
socket = None
threading = None
uuid = None

# The MicroPython test job also imports this module, so CPython-only imports
# stay behind this guard and the test class below is skipped there.
if IS_CPYTHON:
    import threading

    try:
        import socket
        import uuid

        import paho.mqtt.client as mqtt
    except Exception as exc:
        if socket is None and exc.__class__.__module__ == "socket" or "paho" in str(exc).lower() or exc.__class__.__module__.startswith("paho"):
            PAHO_IMPORT_ERROR = exc
        elif "uuid" in str(exc).lower():
            UUID_IMPORT_ERROR = exc
        else:
            PAHO_IMPORT_ERROR = exc


def integration_skip_reason():
    if not IS_CPYTHON:
        return "MQTT integration test only runs under CPython"
    if UUID_IMPORT_ERROR:
        return "uuid support unavailable: %s" % UUID_IMPORT_ERROR
    if PAHO_IMPORT_ERROR or mqtt is None:
        return "paho-mqtt is not installed: %s" % PAHO_IMPORT_ERROR
    return None


def require_real_broker():
    return os.getenv("UHOME_REQUIRE_REAL_BROKER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def assert_or_skip(message):
    if require_real_broker():
        raise AssertionError(message)
    raise unittest.SkipTest(message)


def broker_host():
    return os.getenv("UHOME_INTEGRATION_BROKER_HOST", "127.0.0.1")


def broker_port():
    return int(os.getenv("UHOME_INTEGRATION_BROKER_PORT", "1883"))


def unique_name(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


def wait_until(predicate, timeout, description, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(description)


class PahoUmqttAdapter:
    def __init__(self, client_id, host, port, keepalive=30):
        self.client_id = client_id
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.cb = None
        self.connected = False
        self.sock = None
        self.connect_calls = 0
        self._client = None
        self._connect_event = None
        self._user_disconnect = False
        self._subscriptions = {}
        self._will = None

    def set_callback(self, cb):
        self.cb = cb

    def set_last_will(self, topic, msg, retain=False, qos=0):
        self._will = {
            "topic": topic,
            "msg": msg,
            "retain": retain,
            "qos": qos,
        }
        if self._client is not None:
            self._client.will_set(topic, payload=msg, qos=qos, retain=retain)

    def connect(self, clean_session=True, timeout=None):
        self.connect_calls += 1
        self._disconnect_existing()
        self._connect_event = threading.Event()
        self._user_disconnect = False
        self.connected = False
        self.sock = None
        client = self._build_client(clean_session)
        self._client = client
        client.connect(self.host, self.port, self.keepalive)
        client.loop_start()
        connect_timeout = timeout or 10
        if not self._connect_event.wait(connect_timeout):
            self._disconnect_existing()
            raise OSError("timed out waiting for MQTT CONNACK")
        if not self.connected:
            raise OSError("MQTT connection failed")
        self.sock = client.socket() or getattr(client, "_sock", None)
        return 0

    def disconnect(self):
        self._user_disconnect = True
        self._disconnect_existing()

    def publish(self, topic, msg, retain=False, qos=0):
        client = self._ensure_connected()
        info = client.publish(topic, payload=msg, qos=qos, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise OSError("publish failed with rc=%s" % info.rc)

    def subscribe(self, topic, qos=0):
        client = self._ensure_connected()
        result, mid = client.subscribe(topic, qos=qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise OSError("subscribe failed with rc=%s" % result)
        event = threading.Event()
        self._subscriptions[mid] = event
        if not event.wait(2):
            raise OSError("subscribe to %s timed out" % topic)

    def ping(self):
        self._ensure_connected()

    def check_msg(self):
        self._ensure_connected()

    def _ensure_connected(self):
        if not self.connected or self._client is None:
            raise OSError("MQTT client is disconnected")
        return self._client

    def _build_client(self, clean_session):
        kwargs = {
            "client_id": self.client_id,
            "protocol": mqtt.MQTTv311,
            "clean_session": clean_session,
        }
        if hasattr(mqtt, "CallbackAPIVersion"):
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        client = mqtt.Client(**kwargs)
        if self._will:
            client.will_set(
                self._will["topic"],
                payload=self._will["msg"],
                qos=self._will["qos"],
                retain=self._will["retain"],
            )
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        return client

    def _disconnect_existing(self):
        client = self._client
        self._client = None
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:
            pass
        try:
            client.loop_stop()
        except Exception:
            pass
        self.connected = False
        self.sock = None

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties=None):
        rc = getattr(reason_code, "value", reason_code)
        self.connected = rc == 0
        self.sock = client.socket() or getattr(client, "_sock", None)
        if self._connect_event is not None:
            self._connect_event.set()

    def _on_disconnect(self, _client, _userdata, _disconnect_flags, reason_code, _properties=None):
        self.connected = False
        self.sock = None
        if self._connect_event is not None and not self._connect_event.is_set():
            self._connect_event.set()

    def _on_message(self, _client, _userdata, message):
        if self.cb:
            self.cb(message.topic, message.payload)

    def _on_subscribe(self, _client, _userdata, mid, _granted_qos, _properties=None):
        event = self._subscriptions.pop(mid, None)
        if event is not None:
            event.set()


class ObserverClient:
    def __init__(self, host, port, client_id):
        self._messages = []
        self._condition = threading.Condition()
        self._subscriptions = {}
        kwargs = {
            "client_id": client_id,
            "protocol": mqtt.MQTTv311,
            "clean_session": True,
        }
        if hasattr(mqtt, "CallbackAPIVersion"):
            kwargs["callback_api_version"] = mqtt.CallbackAPIVersion.VERSION2
        self._client = mqtt.Client(**kwargs)
        self._client.on_message = self._on_message
        self._client.on_subscribe = self._on_subscribe
        self._client.connect(host, port, 30)
        self._client.loop_start()

    def close(self):
        try:
            self._client.disconnect()
        finally:
            self._client.loop_stop()

    def subscribe(self, topic):
        result, mid = self._client.subscribe(topic)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise AssertionError("subscribe failed for %s with rc=%s" % (topic, result))
        event = threading.Event()
        self._subscriptions[mid] = event
        if not event.wait(2):
            raise AssertionError("subscribe to %s timed out" % topic)

    def publish(self, topic, payload, retain=False):
        info = self._client.publish(topic, payload=payload, qos=0, retain=retain)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise AssertionError("publish failed for %s with rc=%s" % (topic, info.rc))
        info.wait_for_publish(timeout=2)
        if not info.is_published():
            raise AssertionError("publish to %s timed out" % topic)

    def wait_for(self, predicate, timeout, description):
        deadline = time.time() + timeout
        with self._condition:
            while time.time() < deadline:
                for message in self._messages:
                    if predicate(message):
                        return message
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                self._condition.wait(min(0.1, remaining))
        raise AssertionError(description)

    def count(self, predicate):
        with self._condition:
            return sum(1 for message in self._messages if predicate(message))

    def _on_message(self, _client, _userdata, message):
        payload = message.payload.decode("utf-8", "replace")
        record = {
            "topic": message.topic,
            "payload": payload,
            "retain": bool(message.retain),
        }
        with self._condition:
            self._messages.append(record)
            self._condition.notify_all()

    def _on_subscribe(self, _client, _userdata, mid, _granted_qos, _properties=None):
        event = self._subscriptions.pop(mid, None)
        if event is not None:
            event.set()


class DeviceLoopThread:
    def __init__(self, device, interval=0.05):
        self.device = device
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=5)

    def _run(self):
        while not self.stop_event.is_set():
            self.device.loop()
            time.sleep(self.interval)


@unittest.skipIf(not IS_CPYTHON, "MQTT integration test only runs under CPython")
class UhomeRealBrokerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reason = integration_skip_reason()
        if reason:
            assert_or_skip(reason)
        try:
            with socket.create_connection((broker_host(), broker_port()), timeout=1):
                pass
        except OSError as exc:
            assert_or_skip("MQTT broker at %s:%s is unavailable: %s" % (broker_host(), broker_port(), exc))

    def setUp(self):
        self.observers = []
        self.runners = []
        self.clients = []

    def tearDown(self):
        for runner in self.runners:
            runner.stop()
        for client in self.clients:
            try:
                client.disconnect()
            except Exception:
                pass
        for observer in self.observers:
            observer.close()

    def create_observer(self, prefix):
        observer = ObserverClient(broker_host(), broker_port(), unique_name(prefix))
        self.observers.append(observer)
        return observer

    def create_device_client(self, client_id):
        client = PahoUmqttAdapter(client_id, broker_host(), broker_port(), keepalive=30)
        self.clients.append(client)
        return client

    def create_number_device(self):
        device_name = unique_name("integration_device")
        device = uhome.Device(
            device_name,
            reconnect_min_ms=250,
            reconnect_max_ms=1000,
            connect_timeout=3,
        )
        topic_root = "uhome/tests/%s" % device.id
        number = uhome.Number(
            device,
            "Target Value",
            cmd_t="%s/command" % topic_root,
            stat_t="%s/state" % topic_root,
        )
        received_commands = []

        def on_command(msg):
            received_commands.append(msg)
            number.publish(msg)

        number.set_action(on_command)
        return device, number, received_commands

    def test_device_discovers_handles_commands_and_recovers_after_socket_drop(self):
        device, number, received_commands = self.create_number_device()
        observer = self.create_observer("observer")
        observer.subscribe(number.discovery_topic)
        observer.subscribe(device.will_topic)
        observer.subscribe(number.conf["stat_t"])

        device_client = self.create_device_client(device.id)
        self.assertTrue(device.connect(device_client))

        runner = DeviceLoopThread(device)
        self.runners.append(runner)
        runner.start()

        discovery = observer.wait_for(
            lambda m: m["topic"] == number.discovery_topic,
            timeout=5,
            description="timed out waiting for discovery config",
        )
        config = json.loads(discovery["payload"])
        self.assertEqual(number.conf["cmd_t"], config["cmd_t"])
        self.assertEqual(number.conf["stat_t"], config["stat_t"])
        self.assertEqual(device.will_topic, config["avty_t"])

        observer.wait_for(
            lambda m: m["topic"] == device.will_topic and m["payload"] == "online",
            timeout=5,
            description="timed out waiting for startup availability",
        )

        late_observer = self.create_observer("late_observer")
        late_observer.subscribe(device.will_topic)
        retained_online = late_observer.wait_for(
            lambda m: m["topic"] == device.will_topic and m["payload"] == "online",
            timeout=5,
            description="timed out waiting for retained availability",
        )
        self.assertTrue(retained_online["retain"])

        observer.publish(number.get_topic(), "7")
        wait_until(
            lambda: received_commands == ["7"],
            timeout=5,
            description="device callback did not receive the initial command",
        )
        observer.wait_for(
            lambda m: m["topic"] == number.conf["stat_t"] and m["payload"] == "7",
            timeout=5,
            description="device did not publish state after the initial command",
        )

        initial_online_messages = observer.count(lambda m: m["topic"] == device.will_topic and m["payload"] == "online")
        self.assertGreaterEqual(initial_online_messages, 1)
        initial_discovery_messages = observer.count(lambda m: m["topic"] == number.discovery_topic)

        self.assertIsNotNone(device_client.sock)
        device_client.sock.close()

        wait_until(
            lambda: not device.is_connected,
            timeout=5,
            description="device did not notice the forced socket interruption",
        )
        wait_until(
            lambda: device.is_connected and device_client.connect_calls >= 2,
            timeout=10,
            description="device did not reconnect to the broker in time",
        )

        wait_until(
            lambda: observer.count(lambda m: m["topic"] == device.will_topic and m["payload"] == "online") > initial_online_messages,
            timeout=5,
            description="device did not re-publish online availability after reconnect",
        )
        # uhome publishes "online" before restoring subscriptions and only re-sends
        # discovery once every subscription is acknowledged. Wait for discovery so the
        # QoS 0 command below cannot race ahead of the command-topic SUBSCRIBE.
        wait_until(
            lambda: observer.count(lambda m: m["topic"] == number.discovery_topic) > initial_discovery_messages,
            timeout=5,
            description="device did not re-send discovery after restoring subscriptions",
        )

        observer.publish(number.get_topic(), "13")
        wait_until(
            lambda: received_commands[-1:] == ["13"],
            timeout=5,
            description="device callback did not receive the post-reconnect command",
        )
        observer.wait_for(
            lambda m: m["topic"] == number.conf["stat_t"] and m["payload"] == "13",
            timeout=5,
            description="device did not publish state after reconnect recovery",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
