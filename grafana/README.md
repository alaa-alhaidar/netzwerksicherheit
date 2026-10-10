# PostgreSQL auf dem Pi und Grafana Cloud verbinden

Die Qt-Oberfläche und der Scanner verwenden weiterhin SQLite. Der Dienst `sync`
spiegelt Geräte, Scanverlauf, Pingmessungen und Dienstabfragen alle fünf Sekunden
nach PostgreSQL. Vorhandene Daten werden beim ersten Start übernommen.
Der Scanner muss in der GUI oder als eigener Dienst laufen, damit neue Messungen entstehen.

## 1. PostgreSQL starten

Auf dem Pi im Projektverzeichnis:

```bash
sudo apt update
sudo apt install docker.io docker-compose
sudo systemctl enable --now docker
python3 scripts/setup-postgres.py
sudo bash scripts/start-postgres.sh
```

Das Startskript startet nur `postgres` und `sync`, keinen zweiten Scanner.
Es unterstützt `docker compose` und `docker-compose`. Die erzeugten Passwörter
stehen ausschließlich in `docker/.env` (Dateirechte 600, von Git ausgeschlossen).
Vorhandene Einträge bleiben unverändert. Nicht in Chat oder Git kopieren.

```bash
sudo docker-compose --env-file docker/.env -f docker/compose.yaml --profile postgres logs --tail=30 postgres sync
sudo docker-compose --env-file docker/.env -f docker/compose.yaml exec postgres psql -U monitor_admin -d network_monitor -c 'SELECT count(*) FROM devices;'
```

Datenbank: `network_monitor`; Admin-/Sync-Benutzer: `monitor_admin`;
Grafana-Benutzer: `grafana_reader` mit ausschließlich SELECT-Rechten.
PostgreSQL ist nur über `127.0.0.1:5432` auf dem Pi erreichbar. Der Docker-Dienst
verwendet ein dauerhaftes Volume. `down` erhält es; `down -v` würde es löschen.
Die PostgreSQL-Initialisierung läuft ausschließlich bei einem neuen Volume.
Spätere Änderungen von Passwörtern in `.env` ändern keine bestehenden DB-Benutzer.

## 2. Private Data Source Connect (PDC)

Grafana Cloud kann die lokale Pi-Adresse nicht direkt erreichen. In Grafana:
**Connections → Private data source connections → Add new connection**.
Unter **Configuration Details** einen Token erzeugen; dort stehen Token,
Cluster und Hosted Grafana ID. Diese Werte lokal eintragen:

```bash
cp docker/.env.pdc.example docker/.env.pdc
chmod 600 docker/.env.pdc
nano docker/.env.pdc
sudo docker-compose --env-file docker/.env -f docker/compose.yaml -f docker/compose-pdc.yaml up -d pdc
```

Der PDC-Agent läuft im Hostnetz. Er darf ausschließlich `127.0.0.1:5432`
ansprechen. Es ist keine Router-Portfreigabe für PostgreSQL nötig.
Der Agent braucht ausgehenden Internetzugriff auf die von Grafana genannten
PDC-Endpunkte. Das Agent-Image unterstützt ARM64; `latest` folgt Grafanas Releases.

[Offizielle PDC-Anleitung](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/private-data-source-connect/configure-pdc/)

## 3. PostgreSQL-Datenquelle in Grafana

**Connections → Data sources → Add data source → PostgreSQL**:

- Host: `127.0.0.1:5432` (aus Sicht des PDC-Agenten auf dem Pi).
- Database: `network_monitor`.
- User: `grafana_reader`.
- Password: Wert `GRAFANA_DB_PASSWORD` aus der lokalen `docker/.env`.
- TLS/SSL: `disable` für diese lokale Verbindung über den verschlüsselten PDC-Tunnel.
- Private data source connection: die gerade angelegte PDC-Verbindung auswählen.
- **Save & test** ausführen.

[PostgreSQL-Datenquelle konfigurieren](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/postgres/configure/)

## 4. Dashboard-Panels verbinden

Im vorhandenen Dashboard „Netzwerküberwachung“ die PostgreSQL-Datenquelle wählen
und die SQL-Abfragen aus `grafana/queries.sql` in passende Panels übernehmen.
Die darin verwendeten `$__timeFilter(...)`-Makros werden von Grafana ersetzt.
Es werden keine Panels oder Einstellungen in deinem Cloud-Konto automatisch geändert.

## Betrieb

Ein Datenbankausfall beeinträchtigt lokale Scans nicht. Der Sync-Dienst versucht
die Übertragung erneut; Transaktionen verhindern halbe PostgreSQL-Updates.
Der zuletzt übertragene Scan wird nochmals gelesen, damit später eingetragene
Pingdetails übernommen werden. Nur ein Scanner sollte gleichzeitig schreiben.
Die Spiegelung gehört zu genau einer SQLite-Datenbank; bei deren Austausch oder
Zurücksetzen muss auch der PostgreSQL-Verlauf gezielt neu abgeglichen werden.
