import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class CameraTests(unittest.TestCase):
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

    def test_discovery_config_uses_camera_topic_and_binary_encoding(self):
        device = uhome.Device("Camera Device")
        camera = uhome.Camera(device, "Front Door", entity_category="diagnostic")

        self.assertEqual("camera", camera.entity_type)
        self.assertEqual(camera.topic_for("image"), camera.conf["topic"])
        self.assertEqual("", camera.conf["encoding"])
        self.assertEqual("diagnostic", camera.conf["entity_category"])
        self.assertNotIn("cmd_t", camera.conf)
        self.assertNotIn("stat_t", camera.conf)

    def test_custom_topic_is_preserved(self):
        device = uhome.Device("Camera Device")
        camera = uhome.Camera(device, "Front Door", topic="custom/camera/topic")
        self.assertEqual("custom/camera/topic", camera.conf["topic"])

    def test_publish_jpeg_bytes_as_is(self):
        device = uhome.Device("Camera Device")
        camera = uhome.Camera(device, "Front Door")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        payload = b"\xff\xd8jpeg\xff\xd9"

        self.assertTrue(camera.publish(payload))
        self.assertEqual(camera.conf["topic"], mqtt.published[-1][0])
        self.assertIs(payload, mqtt.published[-1][1])
        self.assertFalse(mqtt.published[-1][2])

    def test_large_image_is_not_cached_for_reconnect_by_default(self):
        device = uhome.Device("Camera Device")
        camera = uhome.Camera(device, "Front Door")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        payload = b"\xff\xd8large\xff\xd9"
        self.assertTrue(camera.publish(payload))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertFalse([p for p in mqtt.published if p[0] == camera.conf["topic"]])

    def test_optional_cached_image_republishes_after_reconnect(self):
        device = uhome.Device("Camera Device")
        camera = uhome.Camera(device, "Front Door")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        payload = b"\xff\xd8small\xff\xd9"
        self.assertTrue(camera.publish(payload, cache=True))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        republished = [p for p in mqtt.published if p[0] == camera.conf["topic"]]
        self.assertEqual(1, len(republished))
        self.assertIs(payload, republished[0][1])


if __name__ == "__main__":
    unittest.main()
