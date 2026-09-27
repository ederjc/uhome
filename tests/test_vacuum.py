import io
import json
import unittest

from test_uhome import FakeClock, FakeMQTTClient, _RedirectStderr

import uhome


class VacuumTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_state_schema_topics(self):
        device = uhome.Device('Vacuum Device')
        vacuum = uhome.Vacuum(device, 'Robot Vacuum', fanspd_lst=['quiet', 'max'])
        self.assertEqual('vacuum', vacuum.entity_type)
        self.assertEqual('state', vacuum.conf['schema'])
        self.assertEqual('Robot Vacuum', vacuum.conf['name'])
        self.assertEqual(device.device, vacuum.conf['dev'])
        self.assertEqual(device.will_topic, vacuum.conf['avty_t'])
        self.assertEqual(vacuum.topic_for('state'), vacuum.conf['stat_t'])
        self.assertEqual(vacuum.topic_for('set'), vacuum.conf['cmd_t'])
        self.assertEqual(vacuum.topic_for('fan_speed/set'), vacuum.conf['set_fan_spd_t'])
        self.assertEqual(vacuum.topic_for('command/send'), vacuum.conf['send_cmd_t'])
        self.assertEqual(vacuum.topic_for('segments/clean'), vacuum.conf['cln_segmnts_cmd_t'])
        self.assertEqual(['quiet', 'max'], vacuum.conf['fanspd_lst'])

    def test_state_schema_json_publishing(self):
        device = uhome.Device('Vacuum Device')
        vacuum = uhome.Vacuum(device, 'Robot Vacuum')
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(vacuum.publish_state('cleaning', battery_level=82, fan_speed='quiet', segments=['kitchen']))

        messages = [payload for topic, payload, retain, qos in mqtt.published if topic == vacuum.conf['stat_t']]
        self.assertEqual(1, len(messages))
        self.assertEqual({'state': 'cleaning', 'battery_level': 82, 'fan_speed': 'quiet', 'segments': ['kitchen']}, json.loads(messages[0]))

    def test_command_callbacks_receive_payloads(self):
        device = uhome.Device('Vacuum Device')
        vacuum = uhome.Vacuum(device, 'Robot Vacuum')
        received = []
        vacuum.set_command_action(lambda msg: received.append(('command', msg)))
        vacuum.set_fan_speed_action(lambda msg: received.append(('fan', msg)))
        vacuum.set_send_command_action(lambda msg: received.append(('send', msg)))
        vacuum.set_clean_segments_action(lambda msg: received.append(('segments', msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(vacuum.get_command_topic(), 'start')
        mqtt.deliver(vacuum.get_fan_speed_topic(), 'max')
        mqtt.deliver(vacuum.get_send_command_topic(), '{"command":"map"}')
        mqtt.deliver(vacuum.get_clean_segments_topic(), '["kitchen"]')
        with _RedirectStderr(io.StringIO()):
            self.assertTrue(device.loop())
            self.assertTrue(device.loop())
            self.assertTrue(device.loop())
            self.assertTrue(device.loop())
        self.assertEqual(
            [
                ('command', 'start'),
                ('fan', 'max'),
                ('send', '{"command":"map"}'),
                ('segments', '["kitchen"]'),
            ],
            received,
        )

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device('Vacuum Device')
        vacuum = uhome.Vacuum(device, 'Robot Vacuum')
        vacuum.set_command_action(lambda msg: None)
        vacuum.set_fan_speed_action(lambda msg: None)
        vacuum.set_send_command_action(lambda msg: None)
        vacuum.set_clean_segments_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.fail_check = True
        self.assertFalse(device.loop())
        mqtt.fail_check = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertIn((vacuum.get_command_topic(), 0), mqtt.subscribed)
        self.assertIn((vacuum.get_fan_speed_topic(), 0), mqtt.subscribed)
        self.assertIn((vacuum.get_send_command_topic(), 0), mqtt.subscribed)
        self.assertIn((vacuum.get_clean_segments_topic(), 0), mqtt.subscribed)


if __name__ == '__main__':
    unittest.main()
