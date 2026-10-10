CREATE TABLE IF NOT EXISTS devices (
    ip TEXT PRIMARY KEY, online INTEGER NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL, last_seen TIMESTAMPTZ NOT NULL,
    last_checked TIMESTAMPTZ NOT NULL, hostname TEXT NOT NULL DEFAULT '',
    mac TEXT NOT NULL DEFAULT '', ping TEXT NOT NULL DEFAULT '',
    services TEXT NOT NULL DEFAULT '', detail_error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS scans (
    id BIGINT PRIMARY KEY, checked TIMESTAMPTZ NOT NULL, networks TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS scans_checked ON scans(checked);
CREATE TABLE IF NOT EXISTS observations (
    scan_id BIGINT NOT NULL REFERENCES scans(id), ip TEXT NOT NULL,
    online INTEGER NOT NULL, ping_ms DOUBLE PRECISION,
    ping_upper_bound INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(scan_id, ip)
);
CREATE INDEX IF NOT EXISTS observations_ip ON observations(ip, scan_id);
CREATE TABLE IF NOT EXISTS service_checks (
    ip TEXT PRIMARY KEY, checked TIMESTAMPTZ NOT NULL, ports JSONB NOT NULL
);
