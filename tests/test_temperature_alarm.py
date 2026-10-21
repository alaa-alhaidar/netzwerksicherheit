from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scanner.temperature_alarm import record_temperature, read_temperature, temperature_in_alarm


class TemperatureAlarmTests(unittest.TestCase):
    def test_inclusive_boundaries_and_outside_values(self):
        for value, active in [(40.9, False), (41, True), (43, True), (45, True), (45.1, False)]:
            with self.subTest(value=value):
                self.assertEqual(temperature_in_alarm((value, 100), now=105), active)

    def test_missing_stale_and_future_values_do_not_trigger(self):
        for reading in [None, (43, 80), (43, 110)]:
            self.assertFalse(temperature_in_alarm(reading, now=100))

    def test_mirror_deduplicates_and_latest_normal_value_clears_alarm(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'monitor.sqlite3'
            self.assertIsNone(read_temperature(path, '192.168.178.124'))
            data = ('lab-01', 'boot', 1, 'fake', 43, 1013, 48, 120000)
            record_temperature(path, '192.168.178.124', data, received_at=100)
            record_temperature(path, '192.168.178.124', data, received_at=120)
            self.assertEqual(read_temperature(path, '192.168.178.124'), (43, 100))
            self.assertTrue(temperature_in_alarm(read_temperature(path, '192.168.178.124'), now=105))
            record_temperature(path, '192.168.178.124',
                               ('lab-01', 'boot', 2, 'fake', 23, 1013, 48, 120000), received_at=110)
            self.assertFalse(temperature_in_alarm(read_temperature(path, '192.168.178.124'), now=111))

class SharedAlarmTests(unittest.TestCase):
    def test_temperature_and_network_share_alarm_output(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from gui.gui import MonitorWindow
        for online, temperature, expected in [(True, 43, True), (False, 23, True),
                                              (False, 43, True), (True, 23, False)]:
            with self.subTest(online=online, temperature=temperature):
                window = SimpleNamespace(
                    db_path='unused', target_ip='192.168.178.124',
                    devices=[dict(ip='192.168.178.124', online=online, ping='2 ms', hostname='Mac')],
                    is_critical=lambda ip: True, led_alarm=Mock(), connection_led=Mock(),
                    offline_popups={}, offline_alerted=set())
                import time
                with patch('gui.gui.read_temperature', return_value=(temperature, time.time())), \
                     patch('gui.gui.QMessageBox') as popup:
                    MonitorWindow.check_critical_devices(window)
                    self.assertEqual(popup.called, expected)

    def test_temperature_recovery_does_not_clear_offline_alarm(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from gui.gui import MonitorWindow
        import time
        popup = Mock()
        window = SimpleNamespace(
            db_path='unused', target_ip='192.168.178.124',
            devices=[dict(ip='192.168.178.124', online=False, ping='keine Antwort')],
            is_critical=lambda ip: True, led_alarm=Mock(), connection_led=Mock(),
            offline_popups={'192.168.178.124': popup}, offline_alerted={'192.168.178.124'})
        with patch('gui.gui.read_temperature', return_value=(23, time.time())):
            MonitorWindow.check_critical_devices(window)
        popup.close.assert_not_called()
        self.assertIn('WLAN', popup.setInformativeText.call_args.args[0])

    def test_temperature_alarm_without_prior_network_scan(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from gui.gui import MonitorWindow
        import time
        window = SimpleNamespace(
            db_path='unused', target_ip='192.168.178.124', devices=[],
            is_critical=lambda ip: True, led_alarm=Mock(), connection_led=Mock(),
            offline_popups={}, offline_alerted=set())
        with patch('gui.gui.read_temperature', return_value=(43, time.time())), \
             patch('gui.gui.QMessageBox') as popup:
            MonitorWindow.check_critical_devices(window)
        self.assertIn('Temperatur', popup.return_value.setInformativeText.call_args.args[0])
