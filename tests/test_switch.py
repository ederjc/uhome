import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

import uhome
from test_uhome import FakeMQTTClient, FakeClock


class SwitchTests(unittest.TestCase):
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

    def test_discovery_config_uses_state_and_command_topics(self):
        device = uhome.Device("Switch Device")
        switch = uhome.Switch(device, "Relay", icon="mdi:power")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        conf = json.loads(self.payload_for(mqtt, switch.discovery_topic))
        self.assertEqual("switch_device_relay", conf["uniq_id"])
        self.assertEqual(switch.topic_for("state"), conf["stat_t"])
        self.assertEqual(switch.topic_for("set"), conf["cmd_t"])
        self.assertEqual("ON", conf["pl_on"])
        self.assertEqual("OFF", conf["pl_off"])
        self.assertEqual("mdi:power", conf["icon"])

    def test_publishes_boolean_state_payloads(self):
        device = uhome.Device("Switch Device")
        switch = uhome.Switch(device, "Relay")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(switch.publish(True))
        self.assertTrue(switch.publish(False))
        self.assertIn((switch.conf["stat_t"], "ON", False, 0), mqtt.published)
        self.assertIn((switch.conf["stat_t"], "OFF", False, 0), mqtt.published)

    def test_command_callback_receives_payload(self):
        device = uhome.Device("Switch Device")
        switch = uhome.Switch(device, "Relay")
        seen = []
        switch.set_action(lambda msg: seen.append(msg))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(switch.get_topic(), "ON")
        self.assertTrue(device.loop())
        self.assertEqual(["ON"], seen)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Switch Device")
        switch = uhome.Switch(device, "Relay")
        switch.set_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((switch.get_topic(), 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
