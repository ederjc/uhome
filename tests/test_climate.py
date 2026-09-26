import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

import uhome
from test_uhome import FakeClock, FakeMQTTClient


class ClimateTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self._old_ticks_ms = uhome.ticks_ms
        self._old_ticks_diff = uhome.ticks_diff
        uhome.ticks_ms = self.clock.ticks_ms
        uhome.ticks_diff = self.clock.ticks_diff

    def tearDown(self):
        uhome.ticks_ms = self._old_ticks_ms
        uhome.ticks_diff = self._old_ticks_diff

    def test_discovery_config_includes_climate_topics(self):
        device = uhome.Device("Climate Device")
        climate = uhome.Climate(device, "Thermostat", modes=["off", "heat"], fan_modes=["auto"], preset_modes=["eco"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        configs = [p for p in mqtt.published if p[0] == climate.discovery_topic]
        self.assertTrue(configs)
        payload = json.loads(configs[-1][1].decode())
        self.assertEqual("climate", climate.entity_type)
        self.assertEqual(["off", "heat"], payload["modes"])
        self.assertEqual(climate.conf["mode_cmd_t"], payload["mode_cmd_t"])
        self.assertEqual(climate.conf["mode_stat_t"], payload["mode_stat_t"])
        self.assertEqual(climate.conf["temp_cmd_t"], payload["temp_cmd_t"])
        self.assertEqual(climate.conf["temp_stat_t"], payload["temp_stat_t"])
        self.assertEqual(climate.conf["curr_temp_t"], payload["curr_temp_t"])
        self.assertEqual(climate.conf["fan_mode_cmd_t"], payload["fan_mode_cmd_t"])
        self.assertEqual(climate.conf["pr_mode_cmd_t"], payload["pr_mode_cmd_t"])

    def test_state_publish(self):
        device = uhome.Device("Climate Device")
        climate = uhome.Climate(device, "Thermostat", modes=["off", "heat"], fan_modes=["auto"], preset_modes=["eco"])
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        self.assertTrue(climate.publish_mode("heat"))
        self.assertTrue(climate.publish_target_temperature(21))
        self.assertTrue(climate.publish_current_temperature(20.5))
        self.assertTrue(climate.publish_fan_mode("auto"))
        self.assertTrue(climate.publish_preset_mode("eco"))
        self.assertIn((climate.conf["mode_stat_t"], "heat", False, 0), mqtt.published)
        self.assertIn((climate.conf["temp_stat_t"], "21", False, 0), mqtt.published)
        self.assertIn((climate.conf["curr_temp_t"], "20.5", False, 0), mqtt.published)
        self.assertIn((climate.conf["fan_mode_stat_t"], "auto", False, 0), mqtt.published)
        self.assertIn((climate.conf["pr_mode_stat_t"], "eco", False, 0), mqtt.published)

    def test_command_handling(self):
        device = uhome.Device("Climate Device")
        climate = uhome.Climate(device, "Thermostat", modes=["off", "heat"], fan_modes=["auto"], preset_modes=["eco"])
        seen = []
        climate.set_mode_action(lambda msg: seen.append(("mode", msg)))
        climate.set_temperature_action(lambda msg: seen.append(("temp", msg)))
        climate.set_fan_mode_action(lambda msg: seen.append(("fan", msg)))
        climate.set_preset_mode_action(lambda msg: seen.append(("preset", msg)))
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.deliver(climate.conf["mode_cmd_t"], "heat")
        mqtt.deliver(climate.conf["temp_cmd_t"], "22")
        mqtt.deliver(climate.conf["fan_mode_cmd_t"], "auto")
        mqtt.deliver(climate.conf["pr_mode_cmd_t"], "eco")
        for _ in range(4):
            device.loop()
        self.assertEqual([("mode", "heat"), ("temp", "22"), ("fan", "auto"), ("preset", "eco")], seen)

    def test_command_subscriptions_survive_reconnect(self):
        device = uhome.Device("Climate Device")
        climate = uhome.Climate(device, "Thermostat", modes=["off", "heat"], fan_modes=["auto"], preset_modes=["eco"])
        climate.set_mode_action(lambda msg: None)
        climate.set_temperature_action(lambda msg: None)
        climate.set_fan_mode_action(lambda msg: None)
        climate.set_preset_mode_action(lambda msg: None)
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()
        mqtt.fail_ping = True
        self.clock.advance(60000)
        self.assertFalse(device.loop())
        mqtt.fail_ping = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())
        self.assertIn((climate.conf["mode_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((climate.conf["temp_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((climate.conf["fan_mode_cmd_t"], 0), mqtt.subscribed)
        self.assertIn((climate.conf["pr_mode_cmd_t"], 0), mqtt.subscribed)


if __name__ == "__main__":
    unittest.main()
