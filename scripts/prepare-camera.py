#!/usr/bin/env python3
"""Build the camera firmware using the Pi's current WLAN, without printing its key."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path('/tmp/esp32-camera-tools')
BOARD = 'esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=huge_app,CDCOnBoot=cdc,USBMode=hwcdc,DebugLevel=verbose'


def read_value(command):
    return subprocess.check_output(command, text=True).rstrip('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interface', default='wlan0')
    args = parser.parse_args()
    profile = read_value(['nmcli', '-g', 'GENERAL.CONNECTION', 'device', 'show', args.interface])
    if not profile or profile == '--':
        raise SystemExit('Der Pi hat keine aktive WLAN-Verbindung.')
    ssid = read_value(['nmcli', '-g', '802-11-wireless.ssid', 'connection', 'show', profile])
    key = read_value(['nmcli', '--show-secrets', '-g', '802-11-wireless-security.psk', 'connection', 'show', profile])
    if not ssid or not key:
        raise SystemExit('WLAN-Zugangsdaten konnten nicht lokal gelesen werden.')
    output = TOOLS / 'camera-build'
    with tempfile.TemporaryDirectory(prefix='camera-source-', dir=TOOLS) as temporary:
        sketch = Path(temporary) / 'esp32_s3_cam'
        shutil.copytree(ROOT / 'firmware/esp32_s3_cam', sketch,
                        ignore=shutil.ignore_patterns('wifi_credentials.h', 'build'))
        credentials = sketch / 'wifi_credentials.h'
        credentials.touch(mode=0o600)
        credentials.write_text('#pragma once\n#define WIFI_SSID ' + json.dumps(ssid, ensure_ascii=False)
                               + '\n#define WIFI_PASSWORD ' + json.dumps(key, ensure_ascii=False) + '\n')
        env = dict(os.environ)
        env['PATH'] = str(TOOLS / 'venv/bin') + ':' + env.get('PATH', '')
        subprocess.run([str(TOOLS / 'arduino-cli'), '--config-file', str(TOOLS / 'arduino-cli.yaml'),
                        'compile', '--fqbn', BOARD, '--build-path', str(output), str(sketch)],
                       env=env, check=True)
    print('Kamera-Firmware gebaut. Zugangsdaten wurden nicht ausgegeben.')
    print('Build-Verzeichnis: ' + str(output))


if __name__ == '__main__':
    main()
