#!/usr/bin/env python3
"""Mirror the local SQLite database into PostgreSQL for Grafana."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import time

import psycopg


def snapshot(path, last_scan):
    if not Path(path).is_file():
        return None
    with closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=5)) as db:
        db.execute('BEGIN')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # Without explicit enrollment there is no authorized sensor export.
        if 'registered_sensors' not in tables:
            return None
        if 'scans' in tables and db.execute('SELECT coalesce(max(id),0) FROM scans').fetchone()[0] < last_scan:
            raise sqlite3.DatabaseError('SQLite-Scanverlauf wurde zurückgesetzt; Zielabgleich erforderlich')
        result = {}
        result['registered_sensors'] = db.execute(
            'SELECT ip,name,enabled FROM registered_sensors').fetchall()
        names = {ip: name for ip, name, enabled in result['registered_sensors'] if enabled}
        columns = 'ip,online,first_seen,last_seen,last_checked,hostname,mac,ping,services,detail_error'
        available = {row[1] for row in db.execute('PRAGMA table_info(devices)')}
        select = ','.join(column if column in available else "''" for column in columns.split(','))
        result['devices'] = db.execute('SELECT ' + select + ' FROM devices').fetchall() if 'devices' in tables else []
        result['scans'] = db.execute('SELECT id,checked,networks FROM scans WHERE id>=? ORDER BY id', (last_scan,)).fetchall() if 'scans' in tables else []
        result['observations'] = db.execute('SELECT scan_id,ip,online,ping_ms,ping_upper_bound FROM observations WHERE scan_id>=?', (last_scan,)).fetchall() if 'observations' in tables else []
        result['service_checks'] = db.execute('SELECT ip,checked,ports FROM service_checks').fetchall() if 'service_checks' in tables else []
        result['devices'] = [row[:5] + (names[row[0]],) + row[6:]
                             for row in result['devices'] if row[0] in names]
        result['observations'] = [row for row in result['observations'] if row[1] in names]
        ids = {row[0] for row in result['observations']}
        result['scans'] = [row for row in result['scans'] if row[0] in ids]
        result['service_checks'] = [row for row in result['service_checks'] if row[0] in names]
        return result


def sync_once(path, connection):
    # Re-copy the latest scan: ping details may arrive after its discovery results.
    last_scan = connection.execute('SELECT coalesce(max(id),0) FROM scans').fetchone()[0]
    data = snapshot(path, last_scan)
    if data is None:
        return False
    previous_ips = {row[0] for row in connection.execute(
        'SELECT ip FROM registered_sensors WHERE enabled=1').fetchall()}
    active_ips = {row[0] for row in data['registered_sensors'] if row[2]}
    if previous_ips != active_ips:
        data = snapshot(path, 0)  # Backfill real measurements of newly enrolled sensors.
    with connection.cursor() as cursor:
        cursor.execute('UPDATE registered_sensors SET enabled=0')
        cursor.executemany('''INSERT INTO registered_sensors(ip,name,enabled) VALUES(%s,%s,%s)
            ON CONFLICT(ip) DO UPDATE SET name=excluded.name,enabled=excluded.enabled''', data['registered_sensors'])
        cursor.executemany('''INSERT INTO devices VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(ip) DO UPDATE SET online=excluded.online, first_seen=excluded.first_seen,
            last_seen=excluded.last_seen,last_checked=excluded.last_checked,hostname=excluded.hostname,
            mac=excluded.mac,ping=excluded.ping,services=excluded.services,detail_error=excluded.detail_error''', data['devices'])
        cursor.executemany('''INSERT INTO scans VALUES (%s,%s,%s) ON CONFLICT(id)
            DO UPDATE SET checked=excluded.checked,networks=excluded.networks''', data['scans'])
        cursor.executemany('''INSERT INTO observations VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT(scan_id,ip) DO UPDATE SET online=excluded.online,
            ping_ms=excluded.ping_ms,ping_upper_bound=excluded.ping_upper_bound''', data['observations'])
        cursor.executemany('''INSERT INTO service_checks VALUES (%s,%s,%s::jsonb)
            ON CONFLICT(ip) DO UPDATE SET checked=excluded.checked,ports=excluded.ports''', data['service_checks'])
        # This database is the sensor mirror. The original SQLite archive stays intact.
        for table in ('observations', 'service_checks', 'devices'):
            cursor.execute(f'''DELETE FROM {table} WHERE NOT EXISTS (
                SELECT 1 FROM registered_sensors r WHERE r.ip={table}.ip AND r.enabled=1)''')
        cursor.execute('''DELETE FROM scans WHERE NOT EXISTS (
            SELECT 1 FROM observations o WHERE o.scan_id=scans.id)''')
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=os.getenv('MONITOR_DB', 'data/monitor.sqlite3'))
    parser.add_argument('--interval', type=int, default=int(os.getenv('SYNC_INTERVAL', '5')))
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if args.interval < 1:
        parser.error('Intervall muss positiv sein')
    while True:
        try:
            # Standard PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD variables are used.
            with psycopg.connect(connect_timeout=10) as connection:
                transferred = sync_once(args.db, connection)
            print('PostgreSQL aktualisiert' if transferred else 'Warte auf Scanner-Daten', flush=True)
        except (psycopg.Error, sqlite3.Error, OSError):
            # Do not log connection strings or passwords.
            print('PostgreSQL-Synchronisierung fehlgeschlagen; erneuter Versuch nach der Pause', flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
