import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_scene_command_topic(self):
        device = uhome.Device("Controller")
        scene = uhome.Scene(device, "Movie Mode", payload_on="ACTIVATE")
        conf = scene.conf
        self.assertEqual(scene.topic_for("set"), conf["cmd_t"])
        self.assertNotIn("stat_t", conf)
        self.assertEqual("ACTIVATE", conf["payload_on"])

        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        payloads = [p for p in mqtt.published if p[0] == scene.discovery_topic]
        self.assertTrue(payloads)
        self.assertEqual(conf, json.loads(payloads[-1][1].decode()))

    def test_scene_activation_callback_receives_payload(self):
        device = uhome.Device("Controller")
        scene = uhome.Scene(device, "Movie Mode")
        received = []
        self.assertTrue(scene.set_action(received.append))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(scene.get_topic(), "ON")
        self.assertTrue(device.loop())
        self.assertEqual(["ON"], received)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Controller")
        scene = uhome.Scene(device, "Movie Mode")
        self.assertTrue(scene.set_action(lambda value: None))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((scene.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
