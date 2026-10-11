# Grafana Cloud mit der erhaltenen PostgreSQL-Datenbank

PostgreSQL verwendet das vorhandene externe Volume `network-monitor_postgres_data`.
Datenbank: `networkdb`; der frühere Besitzer `networkuser` bleibt bestehen.
Der Sync-Benutzer `monitor_sync` erhält SELECT/INSERT/UPDATE auf den Scanner-Tabellen;
`grafana_reader` darf ausschließlich lesen. Die Zugangsdaten stehen lokal in
`docker/.env.cloud` (nicht in Git). Qt arbeitet weiter mit SQLite; `sync` spiegelt
Geräte, Scanverlauf und Dienstabfragen alle fünf Sekunden nach PostgreSQL.

PostgreSQL und Sync starten:

```bash
sudo docker-compose -f docker/compose-cloud.yaml up -d --build postgres sync
```

Diese Konfiguration setzt das bestehende Volume und die bereits eingerichteten
Benutzer voraus. Sie erzeugt keine neue leere Datenbank und ersetzt keine Daten.
Bei Übertragung auf einen neuen Rechner müssen Daten-Volume und Zugangsdaten
separat übernommen werden. Nur ein Scanner soll gleichzeitig schreiben.

## PDC einrichten

In deinem Grafana Cloud:
**Connections → Private data source connections → pdc-breezycaribou3208-default → Configuration Details**.
Einen Token mit `pdc-signing:write` erzeugen und die drei Werte in die lokale Datei
`docker/.env.pdc` eintragen:

```bash
nano docker/.env.pdc
```

```text
GCLOUD_PDC_SIGNING_TOKEN=Token aus Grafana
GCLOUD_PDC_CLUSTER=Wert hinter -cluster
GCLOUD_HOSTED_GRAFANA_ID=Wert hinter -gcloud-hosted-grafana-id
```

Token nicht in Git oder Chat einfügen. Danach:

```bash
sudo docker-compose -f docker/compose-cloud.yaml --profile pdc up -d pdc
```

Der Agent verbindet ausschließlich den lokalen Endpunkt `127.0.0.1:5432` mit
Grafana Cloud. PostgreSQL wird nicht ins Internet oder LAN freigegeben.

## PostgreSQL-Datenquelle in Grafana

| Feld | Wert |
|---|---|
| Host URL | `127.0.0.1:5432` |
| Database | `networkdb` |
| User | `grafana_reader` |
| Password | `GRAFANA_DB_PASSWORD` aus `docker/.env.cloud` |
| TLS/SSL | `disable` für die lokale Strecke im verschlüsselten PDC-Tunnel |
| Version | `17` |
| Min time interval | `5s` |
| TimescaleDB | aus |
| PDC network | `pdc-breezycaribou3208-default` |

Erst wenn Grafana mindestens einen verbundenen PDC-Agenten zeigt, **Save & test**
ausführen. Anschließend im Dashboard die neue PostgreSQL-Datenquelle auswählen.
SQL für die Panels liegt in `grafana/queries.sql`. Grafana-Einstellungen und
bestehende Dashboard-Panels werden von diesen Dateien nicht automatisch geändert.

[Offizielle PDC-Anleitung](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/private-data-source-connect/configure-pdc/)

## Prüfungen

```bash
sudo docker-compose -f docker/compose-cloud.yaml logs --tail=20 sync
sudo docker exec network-postgres psql -U networkuser -d networkdb -c 'SELECT count(*) FROM devices;'
```

Ein vorübergehender Ausfall von PostgreSQL beeinträchtigt lokale Scans nicht;
der Sync-Dienst versucht die Übertragung erneut. Der letzte Scan wird erneut
übertragen, damit nachträglich eingetragene Pingwerte übernommen werden.
SQLite nicht während des laufenden Sync-Dienstes durch eine andere Datenbank ersetzen.

## Fertiges Dashboard importieren

Datei: `grafana/network-monitor-dashboard.json`.
In Grafana **Dashboards → New → Import → Upload dashboard JSON file** wählen,
die Datei hochladen und beim Import die getestete PostgreSQL-Datenquelle auswählen.
Das Dashboard erhält eine neue ID und überschreibt kein vorhandenes Dashboard.
Es enthält neun Panels: Geräte gesamt, online, offline, Alter des letzten Scans,
Erreichbarkeitsverlauf, Pingverlauf, Geräteliste, Erreichbarkeitsquote und Dienste.
Standard: letzte fünf Minuten, automatische Aktualisierung alle fünf Sekunden.
