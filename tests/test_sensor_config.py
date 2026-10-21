from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PyQt6.QtCore import QSettings
from scanner.sensor_config import load_sensor_targets, save_sensor_targets


class SensorConfigTests(unittest.TestCase):
    def test_legacy_devices_migrate_without_losing_names(self):
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory)/'ui-settings.ini'), QSettings.Format.IniFormat)
            settings.setValue('sensor/ip','192.168.1.2')
            settings.setValue('sensor/name','Nano')
            settings.setValue('camera/ip','192.168.1.3')
            settings.setValue('camera/name','Kamera')
            self.assertEqual(load_sensor_targets(settings), {'192.168.1.2':'Nano','192.168.1.3':'Kamera'})

    def test_multiple_devices_survive_restart_and_removed_devices_stay_removed(self):
        with TemporaryDirectory() as directory:
            path=str(Path(directory)/'ui-settings.ini')
            settings=QSettings(path,QSettings.Format.IniFormat)
            targets={f'192.168.1.{index}': f'Gerät {index}' for index in range(2,9)}
            save_sensor_targets(settings,targets)
            restarted=QSettings(path,QSettings.Format.IniFormat)
            self.assertEqual(load_sensor_targets(restarted),targets)
            del targets['192.168.1.3']
            save_sensor_targets(settings,targets)
            self.assertEqual(load_sensor_targets(QSettings(path,QSettings.Format.IniFormat)),targets)
            save_sensor_targets(settings,{})
            self.assertEqual(load_sensor_targets(settings),{})
            self.assertEqual(settings.value('sensor/ip'),'')
            self.assertEqual(settings.value('camera/ip'),'')
