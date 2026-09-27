import io
import unittest

from test_uhome import FakeClock, FakeMQTTClient, _RedirectStderr

import uhome


class AlarmControlPanelTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_alarm_topics(self):
        device = uhome.Device('Alarm Device')
        alarm = uhome.AlarmControlPanel(device, 'Alarm', cod_arm_req=False, cod_dis_req=True)
        self.assertEqual('alarm_control_panel', alarm.entity_type)
        self.assertEqual('Alarm', alarm.conf['name'])
        self.assertEqual(device.device, alarm.conf['dev'])
        self.assertEqual(device.will_topic, alarm.conf['avty_t'])
        self.assertEqual(alarm.topic_for('state'), alarm.conf['stat_t'])
        self.assertEqual(alarm.topic_for('set'), alarm.conf['cmd_t'])
        self.assertFalse(alarm.conf['cod_arm_req'])
        self.assertTrue(alarm.conf['cod_dis_req'])

    def test_state_publishing(self):
        device = uhome.Device('Alarm Device')
        alarm = uhome.AlarmControlPanel(device, 'Alarm')
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(alarm.publish('armed_home'))

        self.assertIn((alarm.conf['stat_t'], 'armed_home', False, 0), mqtt.published)

    def test_command_callback_receives_payload(self):
        device = uhome.Device('Alarm Device')
        alarm = uhome.AlarmControlPanel(device, 'Alarm')
        received = []
        alarm.set_action(lambda msg: received.append(msg))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(alarm.get_topic(), 'ARM_AWAY')
        with _RedirectStderr(io.StringIO()):
            self.assertTrue(device.loop())
        self.assertEqual(['ARM_AWAY'], received)

    def test_command_subscription_survives_reconnect(self):
        device = uhome.Device('Alarm Device')
        alarm = uhome.AlarmControlPanel(device, 'Alarm')
        alarm.set_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.fail_check = True
        self.assertFalse(device.loop())
        mqtt.fail_check = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertIn((alarm.get_topic(), 0), mqtt.subscribed)


if __name__ == '__main__':
    unittest.main()
