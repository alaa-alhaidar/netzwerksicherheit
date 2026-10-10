#!/usr/bin/env python3
"""Create local database credentials without printing or committing them."""
from pathlib import Path
import os
import secrets


def prepare(path):
    path = Path(path)
    existing = path.read_text() if path.exists() else 'NETWORK_CIDR=auto\nSCAN_INTERVAL=60\n'
    keys = {line.split('=', 1)[0].strip() for line in existing.splitlines() if '=' in line and not line.lstrip().startswith('#')}
    additions = []
    for key in ('POSTGRES_PASSWORD', 'GRAFANA_DB_PASSWORD'):
        if key not in keys:
            additions.append(key + '=' + secrets.token_hex(24))
    if additions:
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            output.write(('\n' if existed else existing) + '\n'.join(additions) + '\n')
    path.chmod(0o600)


if __name__ == '__main__':
    prepare(Path(__file__).resolve().parents[1] / 'docker' / '.env')
    print('Lokale PostgreSQL-Konfiguration vorbereitet; Passwörter bleiben in docker/.env.')
