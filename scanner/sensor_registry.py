"""Explicit sensor enrollment shared by the desktop and PostgreSQL exporter."""
import ipaddress
from contextlib import closing
from pathlib import Path
import sqlite3


def register_sensor(path, ip, name):
    """The current desktop supports one manually selected sensor."""
    if ip:
        ip = str(ipaddress.IPv4Address(ip))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS registered_sensors (
            ip TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)''')
        db.execute('UPDATE registered_sensors SET enabled=0')
        if ip:
            db.execute('''INSERT INTO registered_sensors(ip,name,enabled) VALUES(?,?,1)
                ON CONFLICT(ip) DO UPDATE SET name=excluded.name,enabled=1''', (ip, name or 'Sensor'))
