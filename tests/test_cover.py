import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

import uhome
from test_uhome import FakeClock, FakeMQTTClient


class CoverTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_includes_cover_topics_and_position(self):
        device = uhome.Device("Shade Device")
        cover = uhome.Cover(device, "Living Shade", position=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        configs = [p for p in mqtt.published if p[0] == cover.discovery_topic]
        self.assertTrue(configs)
        payload = json.loads(configs[-1][1].decode())
        self.assertEqual("cover", cover.entity_type)
        self.assertEqual(cover.conf["stat_t"], payload["stat_t"])
        self.assertEqual(cover.conf["cmd_t"], payload["cmd_t"])
        self.assertEqual(cover.conf["pos_t"], payload["pos_t"])
        self.assertEqual(cover.conf["set_pos_t"], payload["set_pos_t"])
        self.assertEqual("OPEN", payload["pl_open"])
        self.assertEqual("CLOSE", payload["pl_cls"])
        self.assertEqual("STOP", payload["pl_stop"])

    def test_state_and_position_publish(self):
        device = uhome.Device("Shade Device")
        cover = uhome.Cover(device, "Living Shade", position=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        self.assertTrue(cover.publish("open"))
        self.assertTrue(cover.publish_position(50))
        self.assertIn((cover.conf["stat_t"], "open", False, 0), mqtt.published)
        self.assertIn((cover.conf["pos_t"], "50", False, 0), mqtt.published)

    def test_command_handling(self):
        device = uhome.Device("Shade Device")
        cover = uhome.Cover(device, "Living Shade", position=True)
        seen = []
        cover.set_action(lambda msg: seen.append(("open", msg)), lambda msg: seen.append(("close", msg)), lambda msg: seen.append(("stop", msg)), lambda msg: seen.append(("position", msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.deliver(cover.conf["cmd_t"], "OPEN")
        mqtt.deliver(cover.conf["cmd_t"], "CLOSE")
        mqtt.deliver(cover.conf["cmd_t"], "STOP")
        mqtt.deliver(cover.conf["set_pos_t"], "25")
        for _ in range(4):
            device.loop()
        self.assertEqual([("open", "OPEN"), ("close", "CLOSE"), ("stop", "STOP"), ("position", "25")], seen)

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device("Shade Device")
        cover = uhome.Cover(device, "Living Shade", position=True)
        cover.set_action(lambda msg: None, lambda msg: None, lambda msg: None, lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        mqtt.fail_ping = True
        self.clock.advance(60000)
        self.assertFalse(device.loop())
        mqtt.fail_ping = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((cover.conf["cmd_t"], 0), mqtt.subscribed)
        self.assertIn((cover.conf["set_pos_t"], 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
