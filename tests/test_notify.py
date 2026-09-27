import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "uhome"))

from test_uhome import FakeClock, FakeMQTTClient

import uhome


class NotifyTests(unittest.TestCase):
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

    def test_discovery_config_contains_notify_schema(self):
        device = uhome.Device("Notify Device")
        notify = uhome.Notify(device, "Display", command_template="{{ message }}", retain=True)

        self.assertEqual("Notify Device", notify.conf["dev"]["name"])
        self.assertEqual("notify_device_display", notify.conf["uniq_id"])
        self.assertEqual(device.will_topic, notify.conf["avty_t"])
        self.assertEqual(notify.topic_for("command"), notify.conf["cmd_t"])
        self.assertEqual("{{ message }}", notify.conf["command_template"])
        self.assertTrue(notify.conf["retain"])
        self.assertNotIn("stat_t", notify.conf)

    def test_set_action_subscribes_and_handles_notifications(self):
        device = uhome.Device("Notify Device")
        notify = uhome.Notify(device, "Display")
        received = []
        self.assertTrue(notify.set_action(lambda msg: received.append(msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        self.assertIn((notify.get_topic(), 0), mqtt.subscribed)
        mqtt.deliver(notify.get_topic(), "hello")
        self.assertTrue(device.loop())
        self.assertEqual(["hello"], received)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device("Notify Device")
        notify = uhome.Notify(device, "Display")
        received = []
        notify.set_action(lambda msg: received.append(msg))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.fail_publish = True
        self.assertFalse(device.publish("any/topic", "x"))
        mqtt.fail_publish = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertIn((notify.get_topic(), 0), mqtt.subscribed)
        self.assertTrue(self.payloads_for(mqtt, notify.discovery_topic))
        mqtt.deliver(notify.get_topic(), "after reconnect")
        self.assertTrue(device.loop())
        self.assertEqual(["after reconnect"], received)

    def test_notify_has_no_cached_state_to_republish(self):
        device = uhome.Device("Notify Device")
        notify = uhome.Notify(device, "Display")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(notify.republish())
        self.assertEqual([], mqtt.published)


if __name__ == "__main__":
    unittest.main()
