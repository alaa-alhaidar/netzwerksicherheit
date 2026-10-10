import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock

from scanner.netz_monitor import database
from scanner.sync_postgres import snapshot, sync_once


class PostgresSyncTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name) / 'monitor.sqlite3')
        self.db = database(self.path)
        self.addCleanup(self.db.close)
        with self.db:
            self.db.execute("INSERT INTO devices (ip,online,first_seen,last_seen,last_checked) VALUES ('10.0.0.2',1,'2026-10-10T12:00:00+00:00','2026-10-10T12:00:00+00:00','2026-10-10T12:00:00+00:00')")
            for scan_id in (1, 2):
                self.db.execute('INSERT INTO scans VALUES (?, ?, ?)', (scan_id, '2026-10-10T12:00:00+00:00', '10.0.0.0/24'))
                self.db.execute('INSERT INTO observations VALUES (?, ?, 1, NULL, 0)', (scan_id, '10.0.0.2'))
            self.db.execute('INSERT INTO service_checks VALUES (?, ?, ?)', ('10.0.0.2', '2026-10-10T12:00:00+00:00', json.dumps(['22/SSH'])))

    def test_incremental_snapshot_reloads_latest_ping(self):
        self.assertEqual([row[0] for row in snapshot(self.path, 2)['scans']], [2])
        self.assertIsNone(snapshot(self.path, 2)['observations'][0][3])
        with self.db:
            self.db.execute('UPDATE observations SET ping_ms=1.5 WHERE scan_id=2')
        self.assertEqual(snapshot(self.path, 2)['observations'][0][3], 1.5)

    def test_transfer_uses_parameterized_upserts_in_dependency_order(self):
        connection = MagicMock()
        connection.execute.return_value.fetchone.return_value = (2,)
        cursor = connection.cursor.return_value.__enter__.return_value
        self.assertTrue(sync_once(self.path, connection))
        calls = cursor.executemany.call_args_list
        self.assertEqual(len(calls), 4)
        self.assertIn('INSERT INTO scans', calls[1].args[0])
        self.assertIn('INSERT INTO observations', calls[2].args[0])
        self.assertIn('ON CONFLICT', calls[2].args[0])
        self.assertEqual(calls[2].args[1][0][0], 2)
        self.assertEqual(json.loads(calls[3].args[1][0][2]), ['22/SSH'])

    def test_reset_source_is_rejected_without_silent_history_loss(self):
        with self.assertRaises(sqlite3.DatabaseError):
            snapshot(self.path, 3)

    def test_missing_source_waits(self):
        self.assertIsNone(snapshot(str(Path(self.directory.name) / 'missing'), 0))

    def test_local_credentials_are_private_and_preserved(self):
        spec = importlib.util.spec_from_file_location('setup', 'scripts/setup-postgres.py')
        setup = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(setup)
        path = Path(self.directory.name) / '.env'
        setup.prepare(path)
        first = path.read_text()
        self.assertIn('NETWORK_CIDR=auto', first)
        self.assertIn('GRAFANA_DB_PASSWORD=', first)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        setup.prepare(path)
        self.assertEqual(path.read_text(), first)


if __name__ == '__main__':
    unittest.main()
