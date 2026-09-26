import io
import os
import sys
import unittest


class _RedirectStderr:
    def __init__(self, new_target):
        self._new_target = new_target
        self._old_target = None

    def __enter__(self):
        self._old_target = sys.stderr
        sys.stderr = self._new_target
        return self._new_target

    def __exit__(self, exc_type, exc_value, traceback):
        sys.stderr = self._old_target
        return False


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

import uhome


class FakeClock:
    def __init__(self):
        self.now = 0

    def ticks_ms(self):
        return self.now

    def ticks_diff(self, a, b):
        return a - b

    def advance(self, ms):
        self.now += ms


class FakeMQTTClient:
    def __init__(self, keepalive=60, connect_failures=0):
        self.keepalive = keepalive
        self.connect_failures = connect_failures
        self.connect_calls = 0
        self.clean_sessions = []
        self.timeouts = []
        self.connected = False
        self.cb = None
        self.lw_topic = None
        self.lw_msg = None
        self.lw_retain = False
        self.lw_qos = None
        self.published = []
        self.subscribed = []
        self.pings = 0
        self.disconnects = 0
        self.inbox = []
        self.fail_publish = False
        self.fail_ping = False
        self.fail_check = False
        self.sock = FakeSocket()

    def set_callback(self, cb):
        self.cb = cb

    def set_last_will(self, topic, msg, retain=False, qos=0):
        self.lw_topic = topic
        self.lw_msg = msg
        self.lw_retain = retain
        self.lw_qos = qos

    def connect(self, clean_session=True, timeout=None):
        self.connect_calls += 1
        self.clean_sessions.append(clean_session)
        self.timeouts.append(timeout)
        if self.connect_failures:
            self.connect_failures -= 1
            raise OSError("connect failed")
        self.connected = True
        self.sock = FakeSocket()
        return False

    def disconnect(self):
        self.disconnects += 1
        self.connected = False

    def publish(self, topic, msg, retain=False, qos=0):
        if self.fail_publish:
            raise OSError("publish failed")
        self.published.append((topic, msg, retain, qos))

    def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))

    def ping(self):
        if self.fail_ping:
            raise OSError("ping failed")
        self.pings += 1

    def check_msg(self):
        if self.fail_check:
            raise OSError("check failed")
        if self.inbox:
            topic, msg = self.inbox.pop(0)
            self.cb(topic, msg)

    def deliver(self, topic, msg):
        self.inbox.append((topic, msg))

    def clear_history(self):
        self.published[:] = []
        self.subscribed[:] = []
        self.pings = 0


class FakeSocket:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class RobustFakeMQTTClient(FakeMQTTClient):
    def reconnect(self):
        return self.connect(False)


class UhomeReconnectTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def published_payloads(self, mqtt, topic):
        return [p for p in mqtt.published if p[0] == topic]

    def test_entities_are_per_device_instances(self):
        d1 = uhome.Device("Device One")
        d2 = uhome.Device("Device Two")
        s1 = uhome.Sensor(d1, "Temperature")
        s2 = uhome.Sensor(d2, "Humidity")
        self.assertEqual([s1], d1._entities)
        self.assertEqual([s2], d2._entities)

    def test_entity_creation_before_connect_uses_device_will_topic(self):
        device = uhome.Device("Early Device")
        sensor = uhome.Sensor(device, "Temperature")
        self.assertEqual(device.will_topic, sensor.conf["avty_t"])
        self.assertIn(sensor, device._entities)

    def test_first_connect_failure_then_loop_reconnects_with_backoff(self):
        device = uhome.Device("Retry Device")
        mqtt = FakeMQTTClient(connect_failures=1)
        self.assertFalse(device.connect(mqtt))
        self.assertFalse(device.is_connected)
        self.assertEqual(1, mqtt.connect_calls)

        self.clock.advance(999)
        self.assertFalse(device.loop())
        self.assertEqual(1, mqtt.connect_calls)

        self.clock.advance(1)
        self.assertTrue(device.loop())
        self.assertTrue(device.is_connected)
        self.assertEqual(2, mqtt.connect_calls)
        self.assertEqual([True, True], mqtt.clean_sessions)
        self.assertIn((device.ha_status_topic, 0), mqtt.subscribed)
        self.assertIn((device.will_topic, 0), mqtt.subscribed)
        self.assertIn((device.will_topic, "online", True, 0), mqtt.published)

    def test_publish_failure_reconnect_restores_online_subscriptions_discovery_and_cached_state(self):
        device = uhome.Device("Recover Device")
        sensor = uhome.Sensor(device, "Temperature")
        button = uhome.Button(device, "Identify")
        button.set_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        sensor.publish("21")
        mqtt.clear_history()

        mqtt.fail_publish = True
        old_sock = mqtt.sock
        self.assertFalse(sensor.publish("22"))
        self.assertFalse(device.is_connected)
        self.assertTrue(old_sock.closed)

        mqtt.fail_publish = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((device.will_topic, "online", True, 0), mqtt.published)
        self.assertIn((device.ha_status_topic, 0), mqtt.subscribed)
        self.assertIn((device.will_topic, 0), mqtt.subscribed)
        self.assertIn((button.get_topic(), 0), mqtt.subscribed)
        self.assertTrue(self.published_payloads(mqtt, sensor.discovery_topic))
        self.assertIn((sensor.conf["stat_t"], "22", False, 0), mqtt.published)

    def test_ha_birth_rediscovers_and_republishes_state(self):
        device = uhome.Device("Birth Device")
        sensor = uhome.Sensor(device, "Temperature")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        sensor.publish("20")
        mqtt.clear_history()

        mqtt.deliver(device.ha_status_topic.encode(), b"online")
        self.assertTrue(device.loop())
        self.assertTrue(self.published_payloads(mqtt, sensor.discovery_topic))
        self.assertIn((sensor.conf["stat_t"], "20", False, 0), mqtt.published)

    def test_own_lwt_offline_republishes_online(self):
        device = uhome.Device("Availability Device")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.deliver(device.will_topic, "offline")
        self.assertTrue(device.loop())
        self.assertIn((device.will_topic, "online", True, 0), mqtt.published)

    def test_missing_liveness_echo_marks_dead_and_reconnects(self):
        device = uhome.Device("Liveness Device")
        mqtt = FakeMQTTClient(keepalive=2)
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.clock.advance(1200)
        self.assertTrue(device.loop())
        self.assertEqual(1, mqtt.pings)
        self.assertIn((device.will_topic, "online", True, 0), mqtt.published)

        self.clock.advance(2001)
        old_sock = mqtt.sock
        self.assertFalse(device.loop())
        self.assertFalse(device.is_connected)
        self.assertTrue(old_sock.closed)

        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertEqual(2, mqtt.connect_calls)

    def test_user_callback_exception_does_not_propagate(self):
        device = uhome.Device("Callback Device")
        button = uhome.Button(device, "Identify")

        def boom(msg):
            raise ValueError("bad callback")

        button.set_action(boom)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.deliver(button.get_topic(), "PRESS")
        with _RedirectStderr(io.StringIO()):
            device.loop()
        self.assertTrue(device.is_connected)

    def test_robust_reconnect_hook_runs_on_connect_recovery(self):
        device = uhome.Device("Robust Device")
        sensor = uhome.Sensor(device, "Temperature")
        mqtt = RobustFakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        sensor.publish("19")
        mqtt.clear_history()

        mqtt.reconnect()
        self.assertIn(False, mqtt.clean_sessions)
        self.assertIn((device.will_topic, "online", True, 0), mqtt.published)
        self.assertIn((device.ha_status_topic, 0), mqtt.subscribed)
        self.assertTrue(self.published_payloads(mqtt, sensor.discovery_topic))
        self.assertIn((sensor.conf["stat_t"], "19", False, 0), mqtt.published)


if __name__ == "__main__":
    unittest.main()
