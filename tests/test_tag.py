import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "uhome"))

import uhome
from test_uhome import FakeMQTTClient, FakeClock


class TagScannerTests(unittest.TestCase):
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

    def test_discovery_config_uses_tag_scanner_schema(self):
        device = uhome.Device("Tag Device")
        scanner = uhome.TagScanner(device, "RFID Reader", value_template="{{ value_json.uid }}")

        self.assertEqual("homeassistant/tag/tag_device/rfid_reader/config", scanner.discovery_topic)
        self.assertEqual(scanner.topic_for("scan"), scanner.conf["topic"])
        self.assertEqual("{{ value_json.uid }}", scanner.conf["value_template"])
        self.assertEqual("Tag Device", scanner.conf["device"]["name"])
        self.assertNotIn("name", scanner.conf)
        self.assertNotIn("uniq_id", scanner.conf)
        self.assertNotIn("avty_t", scanner.conf)
        self.assertNotIn("stat_t", scanner.conf)

    def test_scan_publishes_tag_id_without_retain_or_cache(self):
        device = uhome.Device("Tag Device")
        scanner = uhome.TagScanner(device, "RFID Reader")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertTrue(scanner.scan("E9F35959"))
        self.assertIn((scanner.conf["topic"], "E9F35959", False, 0), mqtt.published)
        mqtt.clear_history()
        self.assertTrue(scanner.republish())
        self.assertEqual([], mqtt.published)

    def test_custom_scan_topic_is_used(self):
        device = uhome.Device("Tag Device")
        scanner = uhome.TagScanner(device, "RFID Reader", topic="reader/tag_scanned")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        mqtt.clear_history()

        self.assertEqual("reader/tag_scanned", scanner.get_topic())
        self.assertTrue(scanner.publish("ABC123"))
        self.assertIn(("reader/tag_scanned", "ABC123", False, 0), mqtt.published)

    def test_discovery_is_restored_after_reconnect_but_scan_is_not_replayed(self):
        device = uhome.Device("Tag Device")
        scanner = uhome.TagScanner(device, "RFID Reader")
        mqtt = FakeMQTTClient()
        self.assertTrue(device.connect(mqtt))
        scanner.scan("E9F35959")
        mqtt.clear_history()

        mqtt.fail_publish = True
        self.assertFalse(device.publish("any/topic", "x"))
        mqtt.fail_publish = False
        self.clock.advance(1000)
        self.assertTrue(device.loop())

        self.assertTrue(self.payloads_for(mqtt, scanner.discovery_topic))
        self.assertNotIn((scanner.conf["topic"], "E9F35959", False, 0), mqtt.published)


if __name__ == "__main__":
    unittest.main()
