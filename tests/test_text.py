import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

from test_uhome import FakeClock, FakeMQTTClient
import uhome


class TextTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_text_topics(self):
        device = uhome.Device("Display")
        text = uhome.Text(device, "Message", mode="text", min=1, max=40)
        conf = text.conf
        self.assertEqual(text.topic, conf["stat_t"])
        self.assertEqual(text.topic_for("set"), conf["cmd_t"])
        self.assertEqual("text", conf["mode"])
        self.assertEqual(1, conf["min"])
        self.assertEqual(40, conf["max"])

        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        payloads = [p for p in mqtt.published if p[0] == text.discovery_topic]
        self.assertTrue(payloads)
        self.assertEqual(conf, json.loads(payloads[-1][1].decode()))

    def test_publish_caches_text_state(self):
        device = uhome.Device("Display")
        text = uhome.Text(device, "Message")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(text.publish("Ready"))
        self.assertIn((text.conf["stat_t"], "Ready", False, 0), mqtt.published)

        mqtt.clear_history()
        self.assertTrue(text.republish())
        self.assertIn((text.conf["stat_t"], "Ready", False, 0), mqtt.published)

    def test_command_callback_receives_text(self):
        device = uhome.Device("Display")
        text = uhome.Text(device, "Message")
        received = []
        self.assertTrue(text.set_action(received.append))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(text.get_topic(), "Hello")
        self.assertTrue(device.loop())
        self.assertEqual(["Hello"], received)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Display")
        text = uhome.Text(device, "Message")
        self.assertTrue(text.set_action(lambda value: None))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((text.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
