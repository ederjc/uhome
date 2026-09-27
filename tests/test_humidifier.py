import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class HumidifierTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_includes_humidifier_topics(self):
        device = uhome.Device("Humidifier Device")
        humidifier = uhome.Humidifier(device, "Nursery Humidifier", modes=["normal", "eco"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        configs = [p for p in mqtt.published if p[0] == humidifier.discovery_topic]
        self.assertTrue(configs)
        payload = json.loads(configs[-1][1].decode())
        self.assertEqual("humidifier", humidifier.entity_type)
        self.assertEqual(humidifier.conf["stat_t"], payload["stat_t"])
        self.assertEqual(humidifier.conf["cmd_t"], payload["cmd_t"])
        self.assertEqual(humidifier.conf["hum_cmd_t"], payload["hum_cmd_t"])
        self.assertEqual(humidifier.conf["hum_stat_t"], payload["hum_stat_t"])
        self.assertEqual(humidifier.conf["curr_hum_t"], payload["curr_hum_t"])
        self.assertEqual(["normal", "eco"], payload["modes"])
        self.assertEqual(humidifier.conf["mode_cmd_t"], payload["mode_cmd_t"])

    def test_state_publish(self):
        device = uhome.Device("Humidifier Device")
        humidifier = uhome.Humidifier(device, "Nursery Humidifier", modes=["normal", "eco"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        self.assertTrue(humidifier.publish("ON"))
        self.assertTrue(humidifier.publish_target_humidity(45))
        self.assertTrue(humidifier.publish_current_humidity(42))
        self.assertTrue(humidifier.publish_mode("eco"))
        self.assertIn((humidifier.conf["stat_t"], "ON", False, 0), mqtt.published)
        self.assertIn((humidifier.conf["hum_stat_t"], "45", False, 0), mqtt.published)
        self.assertIn((humidifier.conf["curr_hum_t"], "42", False, 0), mqtt.published)
        self.assertIn((humidifier.conf["mode_stat_t"], "eco", False, 0), mqtt.published)

    def test_command_handling(self):
        device = uhome.Device("Humidifier Device")
        humidifier = uhome.Humidifier(device, "Nursery Humidifier", modes=["normal", "eco"])
        seen = []
        humidifier.set_action(lambda msg: seen.append(("on", msg)), lambda msg: seen.append(("off", msg)))
        humidifier.set_target_humidity_action(lambda msg: seen.append(("target", msg)))
        humidifier.set_mode_action(lambda msg: seen.append(("mode", msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.deliver(humidifier.conf["cmd_t"], "ON")
        mqtt.deliver(humidifier.conf["cmd_t"], "OFF")
        mqtt.deliver(humidifier.conf["hum_cmd_t"], "50")
        mqtt.deliver(humidifier.conf["mode_cmd_t"], "eco")
        for _ in range(4):
            device.loop()
        self.assertEqual([("on", "ON"), ("off", "OFF"), ("target", "50"), ("mode", "eco")], seen)

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device("Humidifier Device")
        humidifier = uhome.Humidifier(device, "Nursery Humidifier", modes=["normal", "eco"])
        humidifier.set_action(lambda msg: None, lambda msg: None)
        humidifier.set_target_humidity_action(lambda msg: None)
        humidifier.set_mode_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        mqtt.fail_ping = True
        self.clock.advance(60000)
        self.assertFalse(device.loop())
        mqtt.fail_ping = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((humidifier.conf["cmd_t"], 0), mqtt.subscribed)
        self.assertIn((humidifier.conf["hum_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((humidifier.conf["mode_cmd_t"], 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
