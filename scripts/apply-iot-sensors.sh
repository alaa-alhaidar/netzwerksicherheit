#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 - <<'PY'
from pathlib import Path
from PyQt6.QtCore import QSettings
from scanner.sensor_registry import register_sensor
path = Path('data/monitor.sqlite3').resolve()
settings = QSettings(str(path.parent / 'ui-settings.ini'), QSettings.Format.IniFormat)
register_sensor(path, settings.value('sensor/ip', ''), settings.value('sensor/name', 'Sensor'))
PY
sudo docker exec -i network-postgres psql -v ON_ERROR_STOP=1 -U networkuser -d networkdb < docker/postgres/iot-sensors.sql
sudo docker compose -f docker/compose-cloud.yaml up -d --build sync
sudo docker compose -f docker/compose-cloud.yaml exec -T sync python sync_postgres.py --once
sudo docker exec -i network-postgres psql -v ON_ERROR_STOP=1 -U networkuser -d networkdb <<'SQL'
BEGIN;
SET LOCAL ROLE grafana_reader;
SELECT ip,hostname,online FROM devices;
SELECT count(*) AS sensor_messdaten FROM devices;
COMMIT;
SQL
