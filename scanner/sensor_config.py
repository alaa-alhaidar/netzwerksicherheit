"""Device-list settings shared by the display and GPIO service."""
import json


def load_sensor_targets(settings):
    raw = settings.value('sensors/list', None)
    if raw is not None:
        entries = json.loads(raw)
        if not isinstance(entries, list):
            raise ValueError('Ungültige gespeicherte Geräteliste.')
        return {entry['ip']: entry.get('name') or 'Sensor' for entry in entries}
    # Preserve the old two-device configuration until the first list save.
    return {ip: settings.value(section + '/name', default)
            for section, default in [('sensor', 'Arduino Nano'), ('camera', 'ESP32-CAM')]
            if (ip := settings.value(section + '/ip', ''))}


def save_sensor_targets(settings, targets):
    settings.setValue('sensors/list', json.dumps([{'ip': ip, 'name': name} for ip, name in targets.items()]))
    # Keep the primary sensor compatible with the existing temperature importer.
    entries = list(targets.items())
    for index, section in enumerate(('sensor', 'camera')):
        ip, name = entries[index] if index < len(entries) else ('', '')
        settings.setValue(section + '/ip', ip)
        settings.setValue(section + '/name', name)
    settings.sync()
