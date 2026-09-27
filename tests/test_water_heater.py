import io
import unittest

from test_uhome import FakeClock, FakeMQTTClient, _RedirectStderr

import uhome


class WaterHeaterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_uses_water_heater_topics(self):
        device = uhome.Device('Heater Device')
        heater = uhome.WaterHeater(device, 'Boiler', modes=['off', 'eco'], min_temp=40)
        self.assertEqual('water_heater', heater.entity_type)
        self.assertEqual('Boiler', heater.conf['name'])
        self.assertEqual(device.device, heater.conf['dev'])
        self.assertEqual(device.will_topic, heater.conf['avty_t'])
        self.assertEqual(heater.topic_for('mode/state'), heater.conf['mode_stat_t'])
        self.assertEqual(heater.topic_for('mode/set'), heater.conf['mode_cmd_t'])
        self.assertEqual(heater.topic_for('temperature/state'), heater.conf['temp_stat_t'])
        self.assertEqual(heater.topic_for('temperature/set'), heater.conf['temp_cmd_t'])
        self.assertEqual(heater.topic_for('current_temperature/state'), heater.conf['curr_temp_t'])
        self.assertEqual(['off', 'eco'], heater.conf['modes'])
        self.assertEqual(40, heater.conf['min_temp'])

    def test_state_publishing_caches_all_state_topics(self):
        device = uhome.Device('Heater Device')
        heater = uhome.WaterHeater(device, 'Boiler')
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(heater.publish_mode('eco'))
        self.assertTrue(heater.publish_target_temperature(55))
        self.assertTrue(heater.publish_current_temperature(48))

        self.assertIn((heater.conf['mode_stat_t'], 'eco', False, 0), mqtt.published)
        self.assertIn((heater.conf['temp_stat_t'], '55', False, 0), mqtt.published)
        self.assertIn((heater.conf['curr_temp_t'], '48', False, 0), mqtt.published)

    def test_mode_and_temperature_command_callbacks(self):
        device = uhome.Device('Heater Device')
        heater = uhome.WaterHeater(device, 'Boiler')
        received = []
        heater.set_mode_action(lambda msg: received.append(('mode', msg)))
        heater.set_temperature_action(lambda msg: received.append(('temperature', msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))

        mqtt.deliver(heater.get_mode_topic(), 'performance')
        mqtt.deliver(heater.get_temperature_topic(), '60')
        with _RedirectStderr(io.StringIO()):
            self.assertTrue(device.loop())
            self.assertTrue(device.loop())
        self.assertEqual([('mode', 'performance'), ('temperature', '60')], received)

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device('Heater Device')
        heater = uhome.WaterHeater(device, 'Boiler')
        heater.set_mode_action(lambda msg: None)
        heater.set_temperature_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        mqtt.fail_check = True
        self.assertFalse(device.loop())
        mqtt.fail_check = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertIn((heater.get_mode_topic(), 0), mqtt.subscribed)
        self.assertIn((heater.get_temperature_topic(), 0), mqtt.subscribed)


if __name__ == '__main__':
    unittest.main()
