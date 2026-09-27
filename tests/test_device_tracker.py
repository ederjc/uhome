import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class DeviceTrackerTests(unittest.TestCase):
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

    def test_discovery_config_uses_state_and_attribute_topics(self):
        device = uhome.Device("Tracker Device")
        tracker = uhome.DeviceTracker(device, "Phone", source_type="gps")

        self.assertEqual("device_tracker", tracker.entity_type)
        self.assertEqual(tracker.topic, tracker.conf["stat_t"])
        self.assertEqual(tracker.topic_for("attributes"), tracker.conf["json_attr_t"])
        self.assertEqual("gps", tracker.conf["source_type"])
        self.assertNotIn("cmd_t", tracker.conf)

    def test_publish_presence_without_attributes(self):
        device = uhome.Device("Tracker Device")
        tracker = uhome.DeviceTracker(device, "Phone")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(tracker.publish("home"))
        self.assertEqual([(tracker.conf["stat_t"], "home", False, 0)], mqtt.published)

    def test_publish_presence_with_gps_attributes(self):
        device = uhome.Device("Tracker Device")
        tracker = uhome.DeviceTracker(device, "Phone")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(tracker.publish("not_home", {"battery": 87}, latitude=48.137, longitude=11.575, gps_accuracy=15))
        self.assertEqual(tracker.conf["stat_t"], mqtt.published[0][0])
        self.assertEqual("not_home", mqtt.published[0][1])
        self.assertEqual(tracker.conf["json_attr_t"], mqtt.published[1][0])
        self.assertEqual(
            {
                "battery": 87,
                "latitude": 48.137,
                "longitude": 11.575,
                "gps_accuracy": 15,
            },
            json.loads(mqtt.published[1][1]),
        )

    def test_cached_presence_and_attributes_republish_after_reconnect(self):
        device = uhome.Device("Tracker Device")
        tracker = uhome.DeviceTracker(device, "Phone")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        self.assertTrue(tracker.publish("home", latitude=48.137, longitude=11.575))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((tracker.conf["stat_t"], "home", False, 0), mqtt.published)
        attr_payloads = [payload for topic, payload, retain, qos in mqtt.published if topic == tracker.conf["json_attr_t"]]
        self.assertEqual({"latitude": 48.137, "longitude": 11.575}, json.loads(attr_payloads[-1]))


if __name__ == "__main__":
    unittest.main()
