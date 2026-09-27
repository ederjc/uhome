import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class SirenTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_siren_topics(self):
        device = uhome.Device("Alarm")
        siren = uhome.Siren(device, "Warning Siren", payload_on="SOUND", payload_off="QUIET")
        conf = siren.conf
        self.assertEqual(siren.topic, conf["stat_t"])
        self.assertEqual(siren.topic_for("set"), conf["cmd_t"])
        self.assertEqual("SOUND", conf["payload_on"])
        self.assertEqual("QUIET", conf["payload_off"])

        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        payloads = [p for p in mqtt.published if p[0] == siren.discovery_topic]
        self.assertTrue(payloads)
        self.assertEqual(conf, json.loads(payloads[-1][1].decode()))

    def test_publish_caches_siren_state(self):
        device = uhome.Device("Alarm")
        siren = uhome.Siren(device, "Warning Siren")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(siren.publish("ON"))
        self.assertIn((siren.conf["stat_t"], "ON", False, 0), mqtt.published)

        mqtt.clear_history()
        self.assertTrue(siren.republish())
        self.assertIn((siren.conf["stat_t"], "ON", False, 0), mqtt.published)

    def test_command_callback_receives_siren_command(self):
        device = uhome.Device("Alarm")
        siren = uhome.Siren(device, "Warning Siren")
        received = []
        self.assertTrue(siren.set_action(received.append))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(siren.get_topic(), "OFF")
        self.assertTrue(device.loop())
        self.assertEqual(["OFF"], received)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Alarm")
        siren = uhome.Siren(device, "Warning Siren")
        self.assertTrue(siren.set_action(lambda value: None))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((siren.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
