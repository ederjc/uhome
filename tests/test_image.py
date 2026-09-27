import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class ImageTests(unittest.TestCase):
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

    def test_discovery_config_can_include_url_and_image_topics(self):
        device = uhome.Device("Image Device")
        image = uhome.Image(device, "Snapshot", content_type="image/jpeg")

        self.assertEqual("image", image.entity_type)
        self.assertEqual(image.topic_for("url"), image.conf["url_t"])
        self.assertEqual(image.topic_for("image"), image.conf["img_t"])
        self.assertEqual("image/jpeg", image.conf["content_type"])
        self.assertNotIn("cmd_t", image.conf)

    def test_discovery_config_can_use_only_url_topic(self):
        device = uhome.Device("Image Device")
        image = uhome.Image(device, "Snapshot", image_topic=False)

        self.assertIn("url_t", image.conf)
        self.assertNotIn("img_t", image.conf)

    def test_publish_url_state(self):
        device = uhome.Device("Image Device")
        image = uhome.Image(device, "Snapshot", image_topic=False)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(image.publish_url("https://example.local/snapshot.jpg"))
        self.assertEqual([(image.conf["url_t"], "https://example.local/snapshot.jpg", False, 0)], mqtt.published)

    def test_publish_binary_image_payload_as_bytes(self):
        device = uhome.Device("Image Device")
        image = uhome.Image(device, "Snapshot", url_topic=False)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        payload = b"\xff\xd8jpeg\xff\xd9"

        self.assertTrue(image.publish_image(payload))
        self.assertEqual(image.conf["img_t"], mqtt.published[-1][0])
        self.assertIs(payload, mqtt.published[-1][1])
        self.assertFalse(mqtt.published[-1][2])

    def test_cached_url_republishes_but_binary_image_is_not_retained(self):
        device = uhome.Device("Image Device")
        image = uhome.Image(device, "Snapshot")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        image.publish_url("https://example.local/snapshot.jpg")
        image.publish_image(b"\xff\xd8large\xff\xd9")
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((image.conf["url_t"], "https://example.local/snapshot.jpg", False, 0), mqtt.published)
        self.assertFalse([p for p in mqtt.published if p[0] == image.conf["img_t"]])


if __name__ == "__main__":
    unittest.main()
