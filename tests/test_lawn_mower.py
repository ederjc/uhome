import io
import unittest

from test_uhome import FakeClock, FakeMQTTClient, _RedirectStderr

import uhome


class LawnMowerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_lawn_mower_topics(self):
        device = uhome.Device('Mower Device')
        mower = uhome.LawnMower(device, 'Garden Mower', opt=False)
        self.assertEqual('lawn_mower', mower.entity_type)
        self.assertEqual('Garden Mower', mower.conf['name'])
        self.assertEqual(device.device, mower.conf['dev'])
        self.assertEqual(device.will_topic, mower.conf['avty_t'])
        self.assertEqual(mower.topic_for('activity/state'), mower.conf['act_stat_t'])
        self.assertEqual(mower.topic_for('start_mowing/set'), mower.conf['strt_mw_cmd_t'])
        self.assertEqual(mower.topic_for('pause/set'), mower.conf['pause_cmd_t'])
        self.assertEqual(mower.topic_for('dock/set'), mower.conf['dock_cmd_t'])
        self.assertFalse(mower.conf['opt'])

    def test_activity_state_publishing(self):
        device = uhome.Device('Mower Device')
        mower = uhome.LawnMower(device, 'Garden Mower')
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(mower.publish_activity('mowing'))

        self.assertIn((mower.conf['act_stat_t'], 'mowing', False, 0), mqtt.published)

    def test_command_callbacks_receive_payloads(self):
        device = uhome.Device('Mower Device')
        mower = uhome.LawnMower(device, 'Garden Mower')
        received = []
        mower.set_start_mowing_action(lambda msg: received.append(('start', msg)))
        mower.set_pause_action(lambda msg: received.append(('pause', msg)))
        mower.set_dock_action(lambda msg: received.append(('dock', msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(mower.get_start_mowing_topic(), 'start_mowing')
        mqtt.deliver(mower.get_pause_topic(), 'pause')
        mqtt.deliver(mower.get_dock_topic(), 'dock')
        with _RedirectStderr(io.StringIO()):
            self.assertTrue(device.loop())
            self.assertTrue(device.loop())
            self.assertTrue(device.loop())
        self.assertEqual([('start', 'start_mowing'), ('pause', 'pause'), ('dock', 'dock')], received)

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device('Mower Device')
        mower = uhome.LawnMower(device, 'Garden Mower')
        mower.set_start_mowing_action(lambda msg: None)
        mower.set_pause_action(lambda msg: None)
        mower.set_dock_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.fail_check = True
        self.assertFalse(device.loop())
        mqtt.fail_check = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertIn((mower.get_start_mowing_topic(), 0), mqtt.subscribed)
        self.assertIn((mower.get_pause_topic(), 0), mqtt.subscribed)
        self.assertIn((mower.get_dock_topic(), 0), mqtt.subscribed)


if __name__ == '__main__':
    unittest.main()
