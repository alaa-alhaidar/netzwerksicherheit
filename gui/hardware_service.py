"""GPIO controller running independently of the display (systemd user service)."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import signal
import sqlite3
import sys

from PyQt6.QtCore import QCoreApplication, QSettings, QTimer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui.led_alarm import LEDAlarm, ConnectionLED
from scanner.temperature_alarm import read_temperature, temperature_in_alarm

# BCM-GPIO für die Alarm-LED; hier im Code ändern.
ALARM_LED_PIN = 17
CONNECTION_LED_PIN = 22


class HardwareController:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.settings = QSettings(str(self.db_path.parent / 'ui-settings.ini'), QSettings.Format.IniFormat)
        self.alarm = LEDAlarm()
        self.connection = ConnectionLED()
        self.connection.configure(True, CONNECTION_LED_PIN)
        self.enabled = None
        self.command_id = None
        self.manual = False
        self.acknowledged = False
        self.reading = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(1000)
        self.refresh()

    def refresh(self):
        self.settings.sync()
        target = self.settings.value('sensor/ip', '')
        targets = [ip for ip in (target, self.settings.value('camera/ip', '')) if ip]
        enabled = self.settings.value('hardware/led_enabled', False, type=bool)
        if enabled != self.enabled:
            self.alarm.configure(enabled, ALARM_LED_PIN)
            self.enabled = enabled
        try:
            state = json.loads((self.db_path.parent / 'pwa-alarm.json').read_text())
            if state.get('command_id') != self.command_id:
                self.command_id = state.get('command_id')
                self.manual = state.get('enabled') is True
                self.acknowledged = not self.manual
        except (OSError, ValueError, AttributeError):
            pass
        try:
            with closing(sqlite3.connect(self.db_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=0.2)) as db:
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='devices'").fetchone()
                devices = {ip: db.execute('SELECT online,ping FROM devices WHERE ip=?', (ip,)).fetchone() if exists else None
                           for ip in targets}
            self.reading = read_temperature(self.db_path, target)
        except (sqlite3.Error, OSError):
            # Keep outputs on transient database failures; try again next second.
            return
        connected = bool(targets) and all(device and device[0] and device[1] != 'keine Antwort' for device in devices.values())
        self.connection.set_active(connected)
        automatic = any(self.settings.value(f'devices/{ip}/critical', True, type=bool)
                        and device and (not device[0] or device[1] == 'keine Antwort')
                        for ip, device in devices.items())
        automatic = automatic or (self.settings.value(f'devices/{target}/critical', True, type=bool)
                                  and temperature_in_alarm(self.reading))
        if not automatic:
            self.acknowledged = False
        self.alarm.set_active(self.manual or (automatic and not self.acknowledged))
        status = {'alarm': self.alarm.status, 'connection': self.connection.status}
        path = self.db_path.parent / 'hardware-status.json'
        try:
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(status))
            temporary.replace(path)
        except OSError:
            pass

    def close(self):
        self.alarm.close()
        self.connection.close()
        (self.db_path.parent / 'hardware-status.json').unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    args = parser.parse_args()
    app = QCoreApplication([])
    controller = HardwareController(args.db)
    app.aboutToQuit.connect(controller.close)
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
