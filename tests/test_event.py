import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class EventTests(unittest.TestCase):
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

    def test_discovery_config_contains_event_schema(self):
        device = uhome.Device("Event Device")
        event = uhome.Event(device, "Doorbell", ["press", "release"], device_class="doorbell")
        self.assertEqual("Event Device", event.conf["dev"]["name"])
        self.assertEqual("event_device_doorbell", event.conf["uniq_id"])
        self.assertEqual(device.will_topic, event.conf["avty_t"])
        self.assertEqual(event.topic, event.conf["stat_t"])
        self.assertEqual(["press", "release"], event.conf["evt_typ"])
        self.assertEqual("doorbell", event.conf["device_class"])

    def test_fire_publishes_json_event_without_retain_or_cache(self):
        device = uhome.Device("Event Device")
        event = uhome.Event(device, "Doorbell", ["press"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(event.fire("press", {"button": "front"}))
        self.assertIn((event.conf["stat_t"], '{"event_type": "press", "button": "front"}', False, 0), mqtt.published)
        mqtt.clear_history()
        self.assertTrue(event.republish())
        self.assertEqual([], mqtt.published)

    def test_discovery_is_restored_after_reconnect_but_event_is_not_replayed(self):
        device = uhome.Device("Event Device")
        event = uhome.Event(device, "Doorbell", ["press"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        event.fire("press")
        mqtt.clear_history()

        mqtt.fail_publish = True
        self.assertFalse(device.publish("any/topic", "x"))
        mqtt.fail_publish = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertTrue(self.payloads_for(mqtt, event.discovery_topic))
        self.assertNotIn((event.conf["stat_t"], '{"event_type": "press"}', False, 0), mqtt.published)


if __name__ == "__main__":
    unittest.main()
