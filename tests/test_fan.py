import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class FanTests(unittest.TestCase):
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

    def test_discovery_config_includes_optional_feature_topics(self):
        device = uhome.Device("Fan Device")
        fan = uhome.Fan(device, "Ceiling Fan", percentage=True, preset_modes=["auto", "sleep"], oscillation=True, direction=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        conf = json.loads(self.payload_for(mqtt, fan.discovery_topic))
        self.assertEqual(fan.topic_for("state"), conf["stat_t"])
        self.assertEqual(fan.topic_for("set"), conf["cmd_t"])
        self.assertEqual(fan.topic_for("percentage/state"), conf["pct_stat_t"])
        self.assertEqual(fan.topic_for("percentage/set"), conf["pct_cmd_t"])
        self.assertEqual(["auto", "sleep"], conf["pr_modes"])
        self.assertEqual(fan.topic_for("preset_mode/state"), conf["pr_mode_stat_t"])
        self.assertEqual(fan.topic_for("preset_mode/set"), conf["pr_mode_cmd_t"])
        self.assertEqual(fan.topic_for("oscillation/state"), conf["osc_stat_t"])
        self.assertEqual(fan.topic_for("oscillation/set"), conf["osc_cmd_t"])
        self.assertEqual(fan.topic_for("direction/state"), conf["dir_stat_t"])
        self.assertEqual(fan.topic_for("direction/set"), conf["dir_cmd_t"])

    def test_publishes_state_and_optional_feature_states(self):
        device = uhome.Device("Fan Device")
        fan = uhome.Fan(device, "Ceiling Fan", percentage=True, preset_modes=["auto"], oscillation=True, direction=True)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(fan.publish(True))
        self.assertTrue(fan.publish_percentage(50))
        self.assertTrue(fan.publish_preset_mode("auto"))
        self.assertTrue(fan.publish_oscillation(True))
        self.assertTrue(fan.publish_direction("forward"))
        self.assertIn((fan.conf["stat_t"], "ON", False, 0), mqtt.published)
        self.assertIn((fan.conf["pct_stat_t"], "50", False, 0), mqtt.published)
        self.assertIn((fan.conf["pr_mode_stat_t"], "auto", False, 0), mqtt.published)
        self.assertIn((fan.conf["osc_stat_t"], "oscillate_on", False, 0), mqtt.published)
        self.assertIn((fan.conf["dir_stat_t"], "forward", False, 0), mqtt.published)

    def test_command_callback_identifies_feature(self):
        device = uhome.Device("Fan Device")
        fan = uhome.Fan(device, "Ceiling Fan", percentage=True, preset_modes=["auto"], oscillation=True, direction=True)
        seen = []
        fan.set_action(lambda feature, msg: seen.append((feature, msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(fan.conf["cmd_t"], "ON")
        mqtt.deliver(fan.conf["pct_cmd_t"], "75")
        mqtt.deliver(fan.conf["pr_mode_cmd_t"], "auto")
        mqtt.deliver(fan.conf["osc_cmd_t"], "oscillate_off")
        mqtt.deliver(fan.conf["dir_cmd_t"], "reverse")
        for _ in range(5):
            self.assertTrue(device.loop())
        self.assertEqual(
            [
                ("state", "ON"),
                ("percentage", "75"),
                ("preset_mode", "auto"),
                ("oscillation", "oscillate_off"),
                ("direction", "reverse"),
            ],
            seen,
        )

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device("Fan Device")
        fan = uhome.Fan(device, "Ceiling Fan", percentage=True, preset_modes=["auto"], oscillation=True, direction=True)
        fan.set_action(lambda feature, msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        device._mark_disconnected()
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((fan.conf["cmd_t"], 0), mqtt.subscribed)
        self.assertIn((fan.conf["pct_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((fan.conf["pr_mode_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((fan.conf["osc_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((fan.conf["dir_cmd_t"], 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
