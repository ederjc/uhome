import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))
sys.path.insert(0, str(ROOT / "tests"))

import uhome
from test_uhome import FakeClock, FakeMQTTClient


class NumberTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_uses_distinct_state_and_command_topics(self):
        device = uhome.Device("Number Device")
        number = uhome.Number(device, "Target Level", min=0, max=100, step=5)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        discovery = [p for p in mqtt.published if p[0] == number.discovery_topic]
        self.assertTrue(discovery)
        config = json.loads(discovery[-1][1].decode("utf-8"))
        self.assertEqual(number.conf["stat_t"], config["stat_t"])
        self.assertEqual(number.conf["cmd_t"], config["cmd_t"])
        self.assertNotEqual(config["stat_t"], config["cmd_t"])
        self.assertEqual(number.topic_for("set"), config["cmd_t"])

    def test_own_state_publish_does_not_trigger_callback(self):
        device = uhome.Device("Number Device")
        number = uhome.Number(device, "Target Level", min=0, max=100, step=5)
        received = []
        number.set_action(received.append)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        self.assertTrue(number.publish(25))
        mqtt.deliver(number.conf["stat_t"], "25")
        self.assertTrue(device.loop())

        self.assertEqual([], received)
        self.assertIn((number.conf["stat_t"], "25", False, 0), mqtt.published)
        self.assertIn((number.conf["cmd_t"], 0), mqtt.subscribed)
        self.assertNotIn((number.conf["stat_t"], 0), mqtt.subscribed)

    def test_command_topic_validates_payload_then_triggers_callback(self):
        device = uhome.Device("Number Device")
        number = uhome.Number(device, "Target Level", min=0, max=100, step=5)
        received = []
        number.set_action(received.append)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(number.conf["cmd_t"], "42")
        mqtt.deliver(number.conf["cmd_t"], "105")
        mqtt.deliver(number.conf["cmd_t"], "43")
        mqtt.deliver(number.conf["cmd_t"], "45")
        self.assertTrue(device.loop())
        self.assertTrue(device.loop())
        self.assertTrue(device.loop())
        self.assertTrue(device.loop())

        self.assertEqual(["45"], received)

    def test_command_subscription_is_restored_after_reconnect(self):
        device = uhome.Device("Number Device")
        number = uhome.Number(device, "Target Level", min=0, max=100, step=5)
        number.set_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.fail_publish = True
        self.assertFalse(number.publish(25))
        mqtt.fail_publish = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertIn((number.conf["cmd_t"], 0), mqtt.subscribed)
        self.assertNotIn((number.conf["stat_t"], 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
