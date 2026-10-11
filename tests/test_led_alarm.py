import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication
from gui.led_alarm import LEDAlarm


class LEDAlarmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.alarm = LEDAlarm()
        self.led, self.factory = Mock(), Mock()

    def tearDown(self):
        self.alarm.close()

    def enable(self):
        with patch('gui.led_alarm.make_led', return_value=(self.led, self.factory)) as make:
            self.alarm.configure(True, 17)
            make.assert_called_once_with(17)

    def test_alarm_blinks_and_recovery_switches_off(self):
        self.enable()
        self.alarm.set_active(True)
        self.led.on.assert_called_once()
        self.assertTrue(self.alarm.timer.isActive())
        self.alarm.toggle()
        self.led.toggle.assert_called_once()
        self.alarm.set_active(False)
        self.assertFalse(self.alarm.timer.isActive())
        self.led.off.assert_called()

    def test_refresh_does_not_restart_blink(self):
        self.enable()
        self.alarm.set_active(True)
        self.alarm.set_active(True)
        self.led.on.assert_called_once()

    def test_enable_during_existing_alarm(self):
        self.alarm.set_active(True)
        self.enable()
        self.assertTrue(self.alarm.timer.isActive())

    def test_disable_and_close_release_gpio(self):
        self.enable()
        self.alarm.set_active(True)
        self.alarm.configure(False)
        self.led.off.assert_called()
        self.led.close.assert_called_once()
        self.factory.close.assert_called_once()
        self.assertFalse(self.alarm.timer.isActive())

    def test_missing_gpio_does_not_crash(self):
        with patch('gui.led_alarm.make_led', side_effect=OSError):
            self.alarm.configure(True)
        self.assertIsNone(self.alarm.led)
        self.assertIn('nicht verfügbar', self.alarm.status)

    def test_runtime_failure_releases_gpio(self):
        self.enable()
        self.alarm.set_active(True)
        self.led.toggle.side_effect = OSError
        self.alarm.toggle()
        self.assertFalse(self.alarm.timer.isActive())
        self.factory.close.assert_called_once()
        self.assertIn('Bildschirmalarme bleiben aktiv', self.alarm.status)


if __name__ == '__main__':
    unittest.main()
