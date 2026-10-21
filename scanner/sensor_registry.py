"""Explicit sensor enrollment shared by the desktop and PostgreSQL exporter."""
import ipaddress
from contextlib import closing
from pathlib import Path
import sqlite3


def register_sensor(path, ip, name):
    """Compatibility helper for selecting one sensor."""
    register_sensors(path, [(ip, name)] if ip else [])


def register_sensors(path, sensors):
    """Replace the enabled selection atomically, preserving archived sensors."""
    cleaned = []
    for ip, name in sensors:
        address = ipaddress.IPv4Address(ip)
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            raise ValueError('Bitte eine gültige Geräte-IP eingeben.')
        cleaned.append((str(address), name or 'Sensor'))
    if len({ip for ip, _ in cleaned}) != len(cleaned):
        raise ValueError('Die Geräte benötigen unterschiedliche IP-Adressen.')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS registered_sensors (
            ip TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)''')
        db.execute('UPDATE registered_sensors SET enabled=0')
        for ip, name in cleaned:
            db.execute('''INSERT INTO registered_sensors(ip,name,enabled) VALUES(?,?,1)
                ON CONFLICT(ip) DO UPDATE SET name=excluded.name,enabled=1''', (ip, name or 'Sensor'))


def enabled_sensors(db):
    exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registered_sensors'").fetchone()
    return db.execute('SELECT ip,name FROM registered_sensors WHERE enabled=1 ORDER BY ip').fetchall() if exists else []
