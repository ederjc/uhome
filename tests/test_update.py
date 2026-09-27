import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        self._old_ticks_add = uhome.ticks_add
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff
        uhome.ticks_add = lambda a, b: a + b

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff
        uhome.ticks_add = self._old_ticks_add

    def test_discovery_config_uses_update_topics(self):
        device = uhome.Device("Update Device")
        update = uhome.Update(device, "Firmware", entity_category="diagnostic")

        self.assertEqual("update", update.entity_type)
        self.assertEqual(update.topic, update.conf["stat_t"])
        self.assertEqual(update.topic_for("command"), update.conf["cmd_t"])
        self.assertEqual("INSTALL", update.conf["pl_inst"])
        self.assertEqual("diagnostic", update.conf["entity_category"])

    def test_publish_installed_and_latest_versions_as_json(self):
        device = uhome.Device("Update Device")
        update = uhome.Update(device, "Firmware")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(update.publish("1.0.0", "1.1.0", title="Firmware 1.1.0"))
        topic, payload, retain, qos = mqtt.published[-1]
        self.assertEqual(update.conf["stat_t"], topic)
        self.assertFalse(retain)
        self.assertEqual(0, qos)
        self.assertEqual(
            {
                "installed_version": "1.0.0",
                "latest_version": "1.1.0",
                "title": "Firmware 1.1.0",
            },
            json.loads(payload),
        )

    def test_install_command_invokes_action(self):
        device = uhome.Device("Update Device")
        update = uhome.Update(device, "Firmware", pl_inst="DO_UPDATE")
        calls = []
        self.assertTrue(update.set_install_action(lambda msg: calls.append(msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(update.get_topic(), "IGNORE")
        self.assertTrue(device.loop())
        mqtt.deliver(update.get_topic(), "DO_UPDATE")
        self.assertTrue(device.loop())
        self.assertEqual(["DO_UPDATE"], calls)

    def test_install_subscription_survives_reconnect(self):
        device = uhome.Device("Update Device")
        update = uhome.Update(device, "Firmware")
        update.set_install_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((update.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
