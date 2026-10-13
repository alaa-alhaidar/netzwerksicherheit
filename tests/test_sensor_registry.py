from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock
import sqlite3

from scanner.netz_monitor import database
from scanner.sensor_registry import register_sensor
from scanner.sync_postgres import snapshot, sync_once


class SensorRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'monitor.sqlite3'

    def tearDown(self):
        self.tmp.cleanup()

    def test_network_devices_do_not_enroll_themselves(self):
        db = database(self.path)
        db.execute("INSERT INTO devices(ip,online,first_seen,last_seen,last_checked) VALUES('192.168.1.99',1,'','','')")
        db.commit(); db.close()
        register_sensor(self.path, '192.168.1.2', 'Sensor')
        data = snapshot(self.path, 0)
        self.assertEqual(data['registered_sensors'], [('192.168.1.2', 'Sensor', 1)])
        self.assertEqual(len(data['devices']), 0)  # Unregistered network devices are never exported.

    def test_sensor_exists_before_first_measurement(self):
        register_sensor(self.path, '192.168.1.2', 'Sensor')
        data = snapshot(self.path, 0)
        self.assertEqual(data['devices'], [])
        self.assertEqual(data['registered_sensors'][0][2], 1)

    def test_switch_disables_previous_sensor(self):
        register_sensor(self.path, '192.168.1.2', 'First')
        register_sensor(self.path, '192.168.1.3', 'Second')
        rows = snapshot(self.path, 0)['registered_sensors']
        self.assertEqual([row for row in rows if row[2]], [('192.168.1.3', 'Second', 1)])

    def test_export_deactivates_missing_entries_before_upsert(self):
        register_sensor(self.path, '192.168.1.2', 'Sensor')
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = (0,)
        cursor = connection.cursor.return_value.__enter__.return_value
        self.assertTrue(sync_once(self.path, connection))
        self.assertEqual(cursor.execute.call_args_list[0].args[0], 'UPDATE registered_sensors SET enabled=0')
        deletes = [call.args[0] for call in cursor.execute.call_args_list if 'DELETE FROM' in call.args[0]]
        self.assertEqual(len(deletes), 4)
        first = cursor.executemany.call_args_list[0]
        self.assertIn('registered_sensors', first.args[0])
        self.assertEqual(first.args[1], [('192.168.1.2', 'Sensor', 1)])

    def test_mirror_contains_one_sensor_and_source_archive_is_preserved(self):
        source = database(self.path)
        stamp = '2026-10-13T10:00:00+00:00'
        for ip in ('192.168.1.2', '192.168.1.99'):
            source.execute('INSERT INTO devices(ip,online,first_seen,last_seen,last_checked) VALUES(?,1,?,?,?)', (ip, stamp, stamp, stamp))
        source.execute('INSERT INTO scans VALUES(1,?,?)', (stamp, '192.168.1.0/24'))
        for ip in ('192.168.1.2', '192.168.1.99'):
            source.execute('INSERT INTO observations VALUES(1,?,1,1.0,0)', (ip,))
        source.commit()
        register_sensor(self.path, '192.168.1.2', 'Sensor')
        mirror = sqlite3.connect(':memory:')
        mirror.execute('PRAGMA foreign_keys=ON')
        mirror.executescript('''
            CREATE TABLE devices(ip TEXT PRIMARY KEY,online INTEGER,first_seen TEXT,last_seen TEXT,
                last_checked TEXT,hostname TEXT,mac TEXT,ping TEXT,services TEXT,detail_error TEXT);
            CREATE TABLE registered_sensors(ip TEXT PRIMARY KEY,name TEXT,enabled INTEGER);
            CREATE TABLE scans(id INTEGER PRIMARY KEY,checked TEXT,networks TEXT);
            CREATE TABLE observations(scan_id INTEGER REFERENCES scans(id),ip TEXT,online INTEGER,
                ping_ms REAL,ping_upper_bound INTEGER,PRIMARY KEY(scan_id,ip));
            CREATE TABLE service_checks(ip TEXT PRIMARY KEY,checked TEXT,ports TEXT);
            INSERT INTO scans VALUES(1,'old','old');
            INSERT INTO devices VALUES('192.168.1.99',1,'old','old','old','','','','','');
            INSERT INTO observations VALUES(1,'192.168.1.99',1,1.0,0);
        ''')
        # Exercise the common INSERT/DELETE SQL on a real transactional SQL engine.
        class Adapter:
            def execute(self, sql, parameters=()):
                return mirror.execute(sql.replace('%s', '?').replace('::jsonb', ''), parameters)
            def executemany(self, sql, rows):
                return mirror.executemany(sql.replace('%s', '?').replace('::jsonb', ''), rows)
            def cursor(self):
                return self
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        try:
            with mirror:
                self.assertTrue(sync_once(self.path, Adapter()))
            self.assertEqual(mirror.execute('SELECT ip,hostname FROM devices').fetchall(), [('192.168.1.2', 'Sensor')])
            self.assertEqual(mirror.execute('SELECT ip FROM observations').fetchall(), [('192.168.1.2',)])
            self.assertEqual(source.execute('SELECT count(*) FROM devices').fetchone()[0], 2)
            self.assertEqual(source.execute('SELECT count(*) FROM observations').fetchone()[0], 2)
        finally:
            source.close()
            mirror.close()


if __name__ == '__main__':
    unittest.main()
