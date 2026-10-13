-- Run once before importing the environmental sensor dashboard.
-- MQTT receiver writes one row per received measurement message.
BEGIN;
CREATE TABLE IF NOT EXISTS sensor_measurements (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_ip TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    temperature_c DOUBLE PRECISION,
    pressure_hpa DOUBLE PRECISION,
    humidity_pct DOUBLE PRECISION CHECK (humidity_pct BETWEEN 0 AND 100),
    gas_resistance_ohm DOUBLE PRECISION CHECK (gas_resistance_ohm >= 0)
);
CREATE INDEX IF NOT EXISTS sensor_measurements_latest_idx
    ON sensor_measurements (sensor_ip, received_at DESC, id DESC);
ALTER TABLE sensor_measurements ADD COLUMN IF NOT EXISTS node_id TEXT;
ALTER TABLE sensor_measurements ADD COLUMN IF NOT EXISTS boot_id TEXT;
ALTER TABLE sensor_measurements ADD COLUMN IF NOT EXISTS sequence BIGINT;
ALTER TABLE sensor_measurements ADD COLUMN IF NOT EXISTS source TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS sensor_measurements_message_idx
    ON sensor_measurements (node_id, boot_id, sequence);
GRANT SELECT ON sensor_measurements TO grafana_reader;
GRANT INSERT ON sensor_measurements TO monitor_sync;
-- ON CONFLICT reads the columns used to identify duplicate messages.
GRANT SELECT (node_id, boot_id, sequence) ON sensor_measurements TO monitor_sync;
GRANT USAGE ON SEQUENCE sensor_measurements_id_seq TO monitor_sync;
COMMIT;
