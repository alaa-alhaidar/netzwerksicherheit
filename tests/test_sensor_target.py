from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scanner.netz_monitor import database, scan_target


class SensorTargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = database(Path(self.tmp.name) / 'monitor.sqlite3')
        self.connection = patch('scanner.netz_monitor.get_connection_info', return_value={})
        self.connection.start()

    def tearDown(self):
        self.connection.stop()
        self.db.close()
        self.tmp.cleanup()

    def test_only_requested_address_is_scanned(self):
        self.db.execute("INSERT INTO devices(ip,online,first_seen,last_seen,last_checked) VALUES('192.168.1.3',1,'','','')")
        self.db.commit()
        info = dict(ip='192.168.1.2', hostname='Mac', mac='', ping='2 ms', detail_error='')
        with patch('scanner.netz_monitor.discover_devices', return_value=['192.168.1.2']) as discover, patch('scanner.netz_monitor.get_device_info', return_value=info):
            scan_target(self.db, '192.168.1.2')
        discover.assert_called_once_with('192.168.1.2/32', 30)
        self.assertEqual(self.db.execute("SELECT online FROM devices WHERE ip='192.168.1.3'").fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT ip,ping_ms FROM observations').fetchall(), [('192.168.1.2', 2.0)])

    def test_unreachable_sensor_is_recorded_without_fake_last_response(self):
        with patch('scanner.netz_monitor.discover_devices', return_value=[]), patch('scanner.netz_monitor.get_device_info') as details:
            scan_target(self.db, '192.168.1.2')
        details.assert_not_called()
        online, ping, last_seen = self.db.execute('SELECT online,ping,last_seen FROM devices').fetchone()
        self.assertEqual((online, ping), (0, 'keine Antwort'))
        self.assertEqual(datetime.fromisoformat(last_seen).timestamp(), 0)

    def test_failed_scan_preserves_existing_status(self):
        with patch('scanner.netz_monitor.discover_devices', side_effect=ValueError('incomplete')):
            with self.assertRaises(ValueError):
                scan_target(self.db, '192.168.1.2')
        self.assertEqual(self.db.execute('SELECT count(*) FROM scans').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
