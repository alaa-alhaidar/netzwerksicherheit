#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/setup-postgres.py
if docker compose version >/dev/null 2>&1; then
    docker compose --env-file docker/.env -f docker/compose.yaml --profile postgres up -d --build postgres sync
else
    docker-compose --env-file docker/.env -f docker/compose.yaml --profile postgres up -d --build postgres sync
fi
