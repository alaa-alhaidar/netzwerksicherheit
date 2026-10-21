import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from PyQt6.QtCore import QCoreApplication, QSettings
from gui.hardware_service import HardwareController
from scanner.netz_monitor import database
from scanner.temperature_alarm import record_temperature

spec = importlib.util.spec_from_file_location('control_services', Path(__file__).resolve().parents[1] / 'scripts/control-services.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class ServiceControlTests(unittest.TestCase):
    def test_pwa_reads_sensor_and_interval_saved_by_gui(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'monitor.sqlite3'
            (db.parent / 'ui-settings.ini').write_text('[sensor]\nip=192.168.1.42\n[scanner]\ninterval=23\n')
            self.assertEqual(control.configured_sensor(db), ('192.168.1.42', 23))

    def setUp(self):
        patcher = patch.object(control, 'uses_pwa_services', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        reset = patch.object(control, 'switch_outputs_off')
        self.reset_outputs = reset.start()
        self.addCleanup(reset.stop)

    def test_native_stop_includes_pwa_units_and_cloud(self):
        with patch.object(control, 'uses_pwa_services', return_value=True), \
             patch.object(control, 'run', return_value='') as run:
            control.control('stop', Path('/tmp/monitor.sqlite3'), '', 60)
        commands = [call.args[0] for call in run.call_args_list]
        for unit in control.PWA_UNITS:
            self.assertIn(['systemctl', '--user', 'stop', unit], commands)
        self.assertIn('pdc', commands[-1])
        self.reset_outputs.assert_called_once()

    def test_stop_leaves_outputs_low_only_after_services_stop(self):
        events = []
        with patch.object(control, 'run', side_effect=lambda *a, **k: events.append('stop')), \
             patch.object(control, 'switch_outputs_off', side_effect=lambda *a: events.append('gpio-off')):
            control.control('stop', Path('/tmp/monitor.sqlite3'), '', 60)
        self.assertEqual(events, ['stop', 'stop', 'gpio-off'])

    def test_failed_stop_does_not_override_active_gpio_owner(self):
        with patch.object(control, 'run', side_effect=RuntimeError('stop failed')):
            with self.assertRaises(RuntimeError):
                control.control('stop', Path('/tmp/monitor.sqlite3'), '', 60)
        self.reset_outputs.assert_not_called()

    def test_native_start_uses_existing_broker_and_gpio_owner(self):
        with patch.object(control, 'uses_pwa_services', return_value=True), \
             patch.object(control, 'run', return_value='') as run:
            control.control('start', Path('/tmp/monitor.sqlite3'), '192.168.1.2', 60)
        commands = [call.args[0] for call in run.call_args_list]
        compose = next(cmd for cmd in commands if 'up' in cmd)
        self.assertNotIn('mqtt', compose)
        self.assertNotIn('telemetry', compose)
        self.assertFalse(any(cmd[0] == 'systemd-run' for cmd in commands))
        self.assertIn('pi-alarm.service', commands[-1])

    def test_start_uses_detached_compose_and_systemd(self):
        with patch.object(control, 'run', return_value='') as run, \
             patch.object(control.subprocess, 'run', return_value=Mock(returncode=3)):
            control.control('start', Path('/tmp/example/monitor.sqlite3'), '192.168.1.2', 17)
        commands = [call.args[0] for call in run.call_args_list]
        compose = next(cmd for cmd in commands if 'up' in cmd)
        self.assertIn('-d', compose)
        worker = next(cmd for cmd in commands if cmd[0] == 'systemd-run')
        self.assertIn('--user', worker)
        self.assertTrue(any('Restart=on-failure' in arg for arg in worker))
        env = run.call_args_list[0].args[1]
        self.assertEqual(env['SENSOR_IP'], '192.168.1.2')
        self.assertEqual(env['SCAN_INTERVAL'], '17')

    def test_failed_preflight_does_not_start_containers(self):
        with patch.object(control, 'run', side_effect=RuntimeError('no user bus')) as run:
            with self.assertRaisesRegex(RuntimeError, 'no user bus'):
                control.control('start', Path('/tmp/monitor.sqlite3'), '192.168.1.2', 60)
        self.assertEqual(run.call_count, 1)

    def test_stop_attempts_containers_even_if_hardware_stop_fails(self):
        with patch.object(control, 'run', side_effect=[RuntimeError('hardware failed'), '']) as run:
            with self.assertRaisesRegex(RuntimeError, 'hardware failed'):
                control.control('stop', Path('/tmp/monitor.sqlite3'), '', 60)
        self.assertIn('stop', run.call_args_list[1].args[0])
        self.assertNotIn('down', run.call_args_list[1].args[0])

    def test_status_reports_missing_and_stopped_containers(self):
        raw = json.dumps({'Service': 'mqtt', 'State': 'running'}) + '\n' + json.dumps({'Service': 'scanner', 'State': 'exited'})
        with patch.object(control, 'run', return_value=raw), \
             patch.object(control.subprocess, 'run', return_value=Mock(stdout='inactive\n')):
            result = control.control('status', Path('/tmp/monitor.sqlite3'), '', 60)
        self.assertEqual(result['services']['scanner'], 'exited')
        self.assertEqual(result['services']['mqtt'], 'running')
        self.assertEqual(result['services']['telemetry'], 'stopped')
        self.assertEqual(result['hardware'], 'inactive')


class BackgroundHardwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'monitor.sqlite3'
        self.ip = '192.168.1.2'
        db = database(self.path)
        db.close()
        settings = QSettings(str(self.path.parent / 'ui-settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('sensor/ip', self.ip)
        settings.setValue('hardware/led_enabled', True)
        settings.sync()
        self.alarm = Mock(status='ready')
        self.connection = Mock(status='ready')
        with patch('gui.hardware_service.LEDAlarm', return_value=self.alarm), \
             patch('gui.hardware_service.ConnectionLED', return_value=self.connection):
            self.worker = HardwareController(self.path)
        self.worker.timer.stop()

    def tearDown(self):
        self.worker.close()
        self.directory.cleanup()

    def measure(self, online, temperature, sequence):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT OR REPLACE INTO devices(ip,online,first_seen,last_seen,last_checked,ping) VALUES(?,?,?,?,?,?)',
                       (self.ip, online, '', '', '', '2 ms' if online else 'keine Antwort'))
        record_temperature(self.path, self.ip, ('node', 'boot', sequence, 'fake', temperature, 1000, 50, 1))
        self.worker.refresh()

    def test_network_and_temperature_alarms_work_without_gui(self):
        for sequence, (online, temperature, expected) in enumerate([(1, 43, True), (0, 23, True), (0, 43, True), (1, 23, False)]):
            self.measure(online, temperature, sequence)
            self.alarm.set_active.assert_called_with(expected)
            self.connection.set_active.assert_called_with(bool(online))

    def test_temperature_alarm_before_first_network_scan(self):
        record_temperature(self.path, self.ip, ('node', 'boot', 1, 'fake', 43, 1000, 50, 1))
        self.worker.refresh()
        self.alarm.set_active.assert_called_with(True)

    def test_manual_acknowledgement_and_new_alarm(self):
        self.measure(0, 23, 0)
        command = self.path.parent / 'pwa-alarm.json'
        command.write_text(json.dumps({'command_id': 'one', 'enabled': False}))
        self.worker.refresh()
        self.alarm.set_active.assert_called_with(False)
        self.measure(1, 23, 1)
        self.measure(0, 23, 2)
        self.alarm.set_active.assert_called_with(True)
        command.write_text(json.dumps({'command_id': 'two', 'enabled': True}))
        self.measure(1, 23, 3)
        self.alarm.set_active.assert_called_with(True)

    def test_setting_change_updates_gpio_without_gui_owning_it(self):
        settings = QSettings(str(self.path.parent / 'ui-settings.ini'), QSettings.Format.IniFormat)
        settings.setValue('hardware/led_enabled', False)
        settings.sync()
        self.worker.refresh()
        self.alarm.configure.assert_called_with(False, 17)
