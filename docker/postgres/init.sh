#!/usr/bin/env bash
set -euo pipefail
: "${GRAFANA_DB_PASSWORD:?Grafana-Lesepasswort fehlt}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv reader_password GRAFANA_DB_PASSWORD
CREATE ROLE grafana_reader LOGIN PASSWORD :'reader_password';
GRANT CONNECT ON DATABASE network_monitor TO grafana_reader;
GRANT USAGE ON SCHEMA public TO grafana_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO grafana_reader;
ALTER ROLE grafana_reader SET default_transaction_read_only = on;
SQL
