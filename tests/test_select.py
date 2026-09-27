import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class SelectTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_select_topics_and_options(self):
        device = uhome.Device("Irrigation")
        select = uhome.Select(device, "Mode", ["off", "auto", "manual"], icon="mdi:form-select")
        conf = select.conf
        self.assertEqual("select", select.entity_type)
        self.assertEqual(select.topic, conf["stat_t"])
        self.assertEqual(select.topic_for("set"), conf["cmd_t"])
        self.assertEqual(["off", "auto", "manual"], conf["ops"])
        self.assertEqual("mdi:form-select", conf["icon"])

        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        payloads = [p for p in mqtt.published if p[0] == select.discovery_topic]
        self.assertTrue(payloads)
        self.assertEqual(conf, json.loads(payloads[-1][1].decode()))

    def test_publish_caches_selected_option(self):
        device = uhome.Device("Irrigation")
        select = uhome.Select(device, "Mode", ["off", "auto", "manual"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(select.publish("auto"))
        self.assertIn((select.conf["stat_t"], "auto", False, 0), mqtt.published)

        mqtt.clear_history()
        self.assertTrue(select.republish())
        self.assertIn((select.conf["stat_t"], "auto", False, 0), mqtt.published)

    def test_command_callback_receives_selected_option(self):
        device = uhome.Device("Irrigation")
        select = uhome.Select(device, "Mode", ["off", "auto", "manual"])
        received = []
        self.assertTrue(select.set_action(received.append))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(select.get_topic(), "manual")
        self.assertTrue(device.loop())
        self.assertEqual(["manual"], received)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Irrigation")
        select = uhome.Select(device, "Mode", ["off", "auto", "manual"])
        self.assertTrue(select.set_action(lambda value: None))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((select.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
