"""Local MQTT temperature mirror for the desktop's shared critical alarm."""
from contextlib import closing
import sqlite3
import time


def record_temperature(path, sensor_ip, data, received_at=None):
    node, boot, sequence, source, temperature, *_ = data
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute('''CREATE TABLE IF NOT EXISTS mqtt_temperatures (
            id INTEGER PRIMARY KEY, sensor_ip TEXT NOT NULL,
            node_id TEXT NOT NULL, boot_id TEXT NOT NULL, sequence INTEGER NOT NULL,
            temperature_c REAL NOT NULL, received_at REAL NOT NULL,
            UNIQUE(node_id,boot_id,sequence))''')
        db.execute('''INSERT OR IGNORE INTO mqtt_temperatures
            (sensor_ip,node_id,boot_id,sequence,temperature_c,received_at)
            VALUES(?,?,?,?,?,?)''',
            (sensor_ip, node, boot, sequence, temperature,
             time.time() if received_at is None else received_at))


def read_temperature(path, sensor_ip):
    with closing(sqlite3.connect(path, timeout=5)) as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mqtt_temperatures'").fetchone()
        if not exists:
            return None
        return db.execute('''SELECT temperature_c,received_at FROM mqtt_temperatures
            WHERE sensor_ip=? ORDER BY received_at DESC,id DESC LIMIT 1''', (sensor_ip,)).fetchone()


def temperature_in_alarm(reading, now=None, max_age=15):
    if reading is None:
        return False
    temperature, received_at = reading
    age = (time.time() if now is None else now) - received_at
    return 0 <= age <= max_age and 41 <= temperature <= 45
