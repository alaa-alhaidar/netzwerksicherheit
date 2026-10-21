#!/usr/bin/env python3
"""Start/stop persistent monitor services; never tie them to the GUI lifetime."""
import argparse
import configparser
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
UNIT = 'network-monitor-hardware.service'
SERVICES = ['scanner', 'mqtt', 'telemetry', 'sync', 'postgres']
PWA_UNITS = ['pi-alarm.service', 'pi-telemetry.service', 'pi-mqtt.service']


def configured_sensor(db):
    settings = configparser.ConfigParser(interpolation=None)
    settings.read(db.parent / 'ui-settings.ini', encoding='utf-8')
    target = settings.get('sensor', 'ip', fallback='') or settings.get('camera', 'ip', fallback='')
    if db.is_file():
        with closing(sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as connection:
            exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registered_sensors'").fetchone()
            if exists:
                rows = connection.execute('SELECT ip FROM registered_sensors WHERE enabled=1 ORDER BY rowid').fetchall()
                addresses = [row[0] for row in rows]
                target = target if target in addresses else (addresses[0] if addresses else '')
    return target, settings.getint('scanner', 'interval', fallback=60)


def uses_pwa_services():
    directory = Path.home() / '.config/systemd/user'
    return all((directory / name).is_file() for name in PWA_UNITS)


def unit_state(name):
    result = subprocess.run(['systemctl', '--user', 'is-active', name],
                            capture_output=True, text=True, timeout=10)
    return result.stdout.strip() or 'inactive'


def switch_outputs_off(env, native):
    """Keep known Pi outputs LOW after gpiozero releases its GPIO claims."""
    pinctrl = shutil.which('pinctrl')
    if not pinctrl:
        if native:
            raise RuntimeError('Dienste gestoppt, aber pinctrl fehlt: LED-Ausgänge konnten nicht auf LOW gesetzt werden.')
        return
    run([pinctrl, 'set', '17,22,27' if native else '17,22', 'op', 'dl'], env, timeout=10)


def run(args, env, timeout=120):
    result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or 'Befehl fehlgeschlagen').strip()[-3000:])
    return result.stdout


def control(action, db, target, interval):
    native = uses_pwa_services()
    docker_services = ['scanner', 'postgres', 'sync', 'pdc'] if native else SERVICES
    env = dict(os.environ, SENSOR_IP=target, SCAN_INTERVAL=str(interval), MONITOR_DATA_DIR=str(db.parent),
               MONITOR_UID=str(os.getuid()), MONITOR_GID=str(os.getgid()))
    compose = ['docker', 'compose', '--env-file', str(ROOT / 'docker/.env'),
               '-f', str(ROOT / 'docker/compose.yaml'), '-f', str(ROOT / 'docker/compose-cloud.yaml'), '--profile', 'pdc']
    if action == 'status':
        raw = run(compose + ['ps', '--all', '--format', 'json'], env, timeout=15).strip()
        rows = json.loads(raw) if raw.startswith('[') else [json.loads(line) for line in raw.splitlines() if line]
        states = {row['Service']: row['State'] for row in rows}
        states = {name: states.get(name, 'stopped') for name in docker_services}
        if native:
            for name, unit in [('mqtt', 'pi-mqtt.service'), ('telemetry', 'pi-telemetry.service')]:
                state = unit_state(unit)
                states[name] = 'running' if state == 'active' else state
        return {'services': states, 'hardware': unit_state('pi-alarm.service' if native else UNIT)}
    if action == 'start':
        if db.name != 'monitor.sqlite3':
            raise ValueError('Die Hintergrunddienste benötigen eine Datenbank namens monitor.sqlite3.')
        ipaddress.IPv4Address(target)
        # Check both service managers before changing anything.
        run(['systemctl', '--user', 'show-environment'], env, timeout=10)
        run(['docker', 'info', '--format', '{{.ServerVersion}}'], env, timeout=15)
        if native:
            # The installed PWA controller already owns GPIO22; don't start a second GPIO owner.
            run(compose + ['up', '-d', '--build'] + docker_services, env, timeout=600)
            run(['systemctl', '--user', 'start', 'pi-mqtt.service', 'pi-telemetry.service', 'pi-alarm.service'], env)
            return {'message': 'PWA- und Hintergrunddienste gestartet.'}
        run(compose + ['up', '-d', '--build'] + docker_services, env, timeout=600)
        active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', UNIT], timeout=10)
        if active.returncode:
            subprocess.run(['systemctl', '--user', 'reset-failed', UNIT], capture_output=True, timeout=10)
            run(['systemd-run', '--user', '--unit=' + UNIT, '--collect',
                 '--property=Restart=on-failure', '--property=RestartSec=3',
                 sys.executable, str(ROOT / 'gui/hardware_service.py'), '--db', str(db)], env, timeout=20)
        return {'message': 'Hintergrunddienste gestartet.'}
    errors = []
    units = PWA_UNITS + [UNIT] if native else [UNIT]
    # Stop installed units separately so an absent optional unit cannot skip the others.
    commands = [['systemctl', '--user', 'stop', unit] for unit in units]
    commands.append(compose + ['stop'] + list(dict.fromkeys(docker_services + SERVICES)))
    for command in commands:
        try:
            run(command, env)
        except RuntimeError as exc:
            if command[0] == 'systemctl' and 'not loaded' in str(exc):
                continue
            # Attempt both even when one service manager fails.
            errors.append(str(exc))
    if errors:
        raise RuntimeError('\n'.join(errors))
    switch_outputs_off(env, native)
    return {'message': 'Hintergrunddienste gestoppt.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--db', required=True)
    parser.add_argument('--target')
    parser.add_argument('--interval', type=int)
    args = parser.parse_args()
    try:
        db = Path(args.db).resolve()
        target, interval = configured_sensor(db)
        target = args.target if args.target is not None else target
        interval = args.interval if args.interval is not None else interval
        if not 1 <= interval <= 86400:
            raise ValueError('Scanpause muss zwischen 1 und 86400 Sekunden liegen.')
        if args.action == 'status':
            result = control(args.action, db, target, interval)
        else:
            # GUI and PWA may issue commands concurrently; apply one complete action at a time.
            db.parent.mkdir(parents=True, exist_ok=True)
            with (db.parent / 'services.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                result = control(args.action, db, target, interval)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, configparser.Error, sqlite3.Error, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
