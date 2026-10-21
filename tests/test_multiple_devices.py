from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scanner.netz_monitor import database
from scanner.sensor_registry import register_sensors, enabled_sensors
from gui.stats_view import load_statistics


class MultipleDevicesTests(unittest.TestCase):
    def test_two_devices_are_enabled_and_validation_preserves_previous_selection(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'monitor.sqlite3'
            sensors = [('192.168.1.2', 'Arduino Nano'), ('192.168.1.3', 'ESP32-CAM')]
            register_sensors(path, sensors)
            with closing(database(path)) as db:
                self.assertEqual(enabled_sensors(db), sensors)
                for invalid in [[('bad', 'Bad')], [('192.168.1.2', 'One'), ('192.168.1.2', 'Two')]]:
                    with self.assertRaises(ValueError):
                        register_sensors(path, invalid)
                    self.assertEqual(enabled_sensors(db), sensors)
                register_sensors(path, sensors[:1])
                self.assertEqual(enabled_sensors(db), sensors[:1])

    def test_statistics_include_both_devices_and_exclude_other_addresses(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'monitor.sqlite3'
            with closing(database(path)) as db, db:
                for ip in ['192.168.1.2', '192.168.1.3', '192.168.1.99']:
                    db.execute('INSERT INTO devices(ip,online,first_seen,last_seen,last_checked) VALUES(?,1,?,?,?)', (ip, '2099', '2099', '2099'))
                    db.execute('INSERT INTO scans(checked,networks) VALUES(?,?)', ('2099', ip))
                    scan_id = db.execute('SELECT max(id) FROM scans').fetchone()[0]
                    db.execute('INSERT INTO observations(scan_id,ip,online) VALUES(?,?,1)', (scan_id,ip))
            data = load_statistics(path, 24, ['192.168.1.2','192.168.1.3'])
            self.assertEqual({row['ip'] for row in data['devices']}, {'192.168.1.2','192.168.1.3'})
            self.assertEqual(len(data['history']),2)
            self.assertEqual(len(data['availability']),2)
            self.assertEqual(load_statistics(path,24,[])['devices'],[])
