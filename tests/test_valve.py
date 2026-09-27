import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class ValveTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_includes_valve_topics(self):
        device = uhome.Device("Valve Device")
        valve = uhome.Valve(device, "Irrigation Valve", reports_position=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        configs = [p for p in mqtt.published if p[0] == valve.discovery_topic]
        self.assertTrue(configs)
        payload = json.loads(configs[-1][1].decode())
        self.assertEqual("valve", valve.entity_type)
        self.assertEqual(valve.conf["stat_t"], payload["stat_t"])
        self.assertEqual(valve.conf["cmd_t"], payload["cmd_t"])
        self.assertEqual("OPEN", payload["pl_open"])
        self.assertEqual("CLOSE", payload["pl_cls"])
        self.assertEqual("STOP", payload["pl_stop"])
        self.assertTrue(payload["reports_position"])

    def test_state_publish(self):
        device = uhome.Device("Valve Device")
        valve = uhome.Valve(device, "Irrigation Valve", reports_position=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        self.assertTrue(valve.publish("open"))
        self.assertTrue(valve.publish_position(50))
        self.assertIn((valve.conf["stat_t"], "open", False, 0), mqtt.published)
        self.assertIn((valve.conf["stat_t"], "50", False, 0), mqtt.published)

    def test_command_handling(self):
        device = uhome.Device("Valve Device")
        valve = uhome.Valve(device, "Irrigation Valve", reports_position=True)
        seen = []
        valve.set_action(
            lambda msg: seen.append(("open", msg)),
            lambda msg: seen.append(("close", msg)),
            lambda msg: seen.append(("stop", msg)),
            lambda msg: seen.append(("position", msg)),
        )
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.deliver(valve.conf["cmd_t"], "OPEN")
        mqtt.deliver(valve.conf["cmd_t"], "CLOSE")
        mqtt.deliver(valve.conf["cmd_t"], "STOP")
        mqtt.deliver(valve.conf["cmd_t"], "75")
        for _ in range(4):
            device.loop()
        self.assertEqual([("open", "OPEN"), ("close", "CLOSE"), ("stop", "STOP"), ("position", "75")], seen)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Valve Device")
        valve = uhome.Valve(device, "Irrigation Valve", reports_position=True)
        valve.set_action(lambda msg: None, lambda msg: None, lambda msg: None, lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        mqtt.fail_ping = True
        self.clock.advance(60000)
        self.assertFalse(device.loop())
        mqtt.fail_ping = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((valve.conf["cmd_t"], 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
