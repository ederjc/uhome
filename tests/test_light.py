import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

import uhome
from test_uhome import FakeMQTTClient, FakeClock


class LightTests(unittest.TestCase):
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

    def payload_for(self, mqtt, topic):
        for published in mqtt.published:
            if published[0] == topic:
                payload = published[1]
                if isinstance(payload, bytes):
                    payload = payload.decode()
                return payload
        self.fail("topic not published: %s" % topic)

    def test_discovery_config_uses_json_schema_and_optional_features(self):
        device = uhome.Device("Light Device")
        light = uhome.Light(device, "Desk Lamp", color_temp=True, rgb=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        conf = json.loads(self.payload_for(mqtt, light.discovery_topic))
        self.assertEqual("json", conf["schema"])
        self.assertEqual(light.topic_for("state"), conf["stat_t"])
        self.assertEqual(light.topic_for("set"), conf["cmd_t"])
        self.assertTrue(conf["brightness"])
        self.assertTrue(conf["color_temp"])
        self.assertTrue(conf["rgb"])

    def test_publishes_json_state(self):
        device = uhome.Device("Light Device")
        light = uhome.Light(device, "Desk Lamp", color_temp=True, rgb=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(light.publish("ON", brightness=123, color_temp=300, rgb=(1, 2, 3)))
        payload = json.loads(self.payload_for(mqtt, light.conf["stat_t"]))
        self.assertEqual("ON", payload["state"])
        self.assertEqual(123, payload["brightness"])
        self.assertEqual(300, payload["color_temp"])
        self.assertEqual({"r": 1, "g": 2, "b": 3}, payload["color"])

    def test_command_callback_receives_decoded_json(self):
        device = uhome.Device("Light Device")
        light = uhome.Light(device, "Desk Lamp")
        seen = []
        light.set_action(lambda cmd: seen.append(cmd))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(light.get_topic(), json.dumps({"state": "ON", "brightness": 200}))
        self.assertTrue(device.loop())
        self.assertEqual([{"state": "ON", "brightness": 200}], seen)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Light Device")
        light = uhome.Light(device, "Desk Lamp")
        light.set_action(lambda cmd: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((light.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
