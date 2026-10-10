#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --env-file docker/.env -f docker/compose.yaml up -d --build
