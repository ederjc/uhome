import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

import uhome
from test_uhome import FakeMQTTClient, FakeClock


class DeviceTriggerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def payloads_for(self, mqtt, topic):
        return [payload for pub_topic, payload, retain, qos in mqtt.published if pub_topic == topic]

    def test_discovery_config_uses_device_automation_schema(self):
        device = uhome.Device("Remote Device", manufacturer="Example")
        trigger = uhome.DeviceTrigger(device, "Left Click", "action", "arrow_left_click", payload="arrow_left_click")

        self.assertEqual("homeassistant/device_automation/remote_device/left_click/config", trigger.discovery_topic)
        self.assertEqual("trigger", trigger.conf["automation_type"])
        self.assertEqual(trigger.topic_for("trigger"), trigger.conf["topic"])
        self.assertEqual("action", trigger.conf["type"])
        self.assertEqual("arrow_left_click", trigger.conf["subtype"])
        self.assertEqual("arrow_left_click", trigger.conf["payload"])
        self.assertEqual("Remote Device", trigger.conf["device"]["name"])
        self.assertNotIn("name", trigger.conf)
        self.assertNotIn("uniq_id", trigger.conf)
        self.assertNotIn("avty_t", trigger.conf)
        self.assertNotIn("stat_t", trigger.conf)

    def test_trigger_publishes_payload_without_retain_or_cache(self):
        device = uhome.Device("Remote Device")
        trigger = uhome.DeviceTrigger(device, "Left Click", "action", "arrow_left_click", payload="arrow_left_click")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(trigger.trigger())
        self.assertIn((trigger.conf["topic"], "arrow_left_click", False, 0), mqtt.published)
        mqtt.clear_history()
        self.assertTrue(trigger.republish())
        self.assertEqual([], mqtt.published)

    def test_can_publish_custom_payload_to_custom_topic(self):
        device = uhome.Device("Remote Device")
        trigger = uhome.DeviceTrigger(device, "Battery Button", "button_short_press", "button_1", topic="remote/action")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertEqual("remote/action", trigger.get_topic())
        self.assertTrue(trigger.publish("pressed"))
        self.assertIn(("remote/action", "pressed", False, 0), mqtt.published)

    def test_discovery_is_restored_after_reconnect_but_trigger_is_not_replayed(self):
        device = uhome.Device("Remote Device")
        trigger = uhome.DeviceTrigger(device, "Left Click", "action", "arrow_left_click", payload="arrow_left_click")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        trigger.trigger()
        mqtt.clear_history()

        mqtt.fail_publish = True
        self.assertFalse(device.publish("any/topic", "x"))
        mqtt.fail_publish = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertTrue(self.payloads_for(mqtt, trigger.discovery_topic))
        self.assertNotIn((trigger.conf["topic"], "arrow_left_click", False, 0), mqtt.published)


if __name__ == "__main__":
    unittest.main()
