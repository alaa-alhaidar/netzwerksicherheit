-- Prepare the PostgreSQL sensor mirror; measurements are updated by the exporter.
BEGIN;
CREATE TABLE IF NOT EXISTS registered_sensors (
    ip TEXT PRIMARY KEY, name TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
);
GRANT SELECT, INSERT, UPDATE ON registered_sensors TO monitor_sync;
GRANT SELECT ON registered_sensors TO grafana_reader;
GRANT DELETE ON devices, observations, scans, service_checks TO monitor_sync;
COMMIT;
