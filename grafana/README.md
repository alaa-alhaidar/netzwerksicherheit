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

## IoT: PostgreSQL enthält nur manuell eingetragene Sensoren

Grafana verwendet weiterhin dieselbe PostgreSQL-Datenquelle und dieselben Tabellen.
Der Abgleich exportiert nur aktivierte Einträge aus `registered_sensors` sowie deren
wirkliche Messungen. Andere Geräte, Beobachtungen und Dienste werden aus dem
PostgreSQL-Monitor entfernt. Das ursprüngliche SQLite-Archiv bleibt auf dem Pi
bestehen; seine übrigen Netzwerkgeräte werden nicht erneut exportiert.

Einmal auf dem Pi im Projektverzeichnis ausführen:

```bash
bash scripts/apply-iot-sensors.sh
```

Das Skript übernimmt die manuelle Sensorwahl aus den Einstellungen, legt die
PostgreSQL-Sensorliste an, vergibt die notwendigen Rechte für den Abgleich und
startet dessen aktualisiertes Docker-Image. Anschließend zeigt es den tatsächlichen
Inhalt von `devices` und die Zahl der Sensoren mit Messdaten. Docker benötigt sudo.

Ein erneuter Dashboard-Import ist für die korrigierte Zählung nicht nötig. Das
bestehende Dashboard liest anschließend nur noch den ausgewählten Sensor aus
PostgreSQL. Ein noch nicht gemessener Sensor wird nicht als online erfunden und
erscheint in `devices` erst nach seiner ersten Prüfung. Beim Wechsel des Sensors
werden die Messungen des neuen Sensors aus dem lokalen Archiv übernommen.

## Einzelgerät 192.168.178.124

Das Dashboard und die Beispielabfragen zeigen ausschließlich `192.168.178.124`, auch wenn ältere Geräte in der Datenbank gespeichert sind. Das geänderte Dashboard-JSON erneut in Grafana importieren. Der Scanner in `docker/compose.yaml` verwendet `--target-ip 192.168.178.124` und scannt nur diese Adresse (`/32`). Die Qt-Oberfläche nutzt ebenfalls das konfigurierte Sensorziel. Nach Änderung der Compose-Datei den Scanner mit `scripts/start.sh` neu starten, sofern dieser statt der Qt-Oberfläche verwendet wird.

## Umweltmonitor mit vier Messwerten

Das Dashboard enthält oben Geräte gesamt, Online und Offline für `.124` und darunter
vier große Kacheln: Temperatur (°C), Luftdruck (hPa), Luftfeuchtigkeit (%) und
Gaswiderstand (Ω). Die Statuszahlen stammen weiterhin vom Netzwerk-Scanner.

Vor dem Import die neue Messwerttabelle anlegen:

```bash
sudo docker exec -i network-postgres psql -v ON_ERROR_STOP=1 -U networkuser -d networkdb < docker/postgres/sensor-measurements.sql
```

Anschließend `grafana/network-monitor-dashboard.json` in Grafana importieren.
Der spätere Push-Empfänger muss echte Messwerte in `sensor_measurements` schreiben:
`sensor_ip = '192.168.178.124'`, `temperature_c`, `pressure_hpa`, `humidity_pct`,
`gas_resistance_ohm`; `received_at` ist die Empfangszeit. Der Nachrichtenvertrag
steht in `docs/iot-architektur.md`. Der MQTT-Empfänger nutzt den vorhandenen Sync-Benutzer; die SQL-Datei ergänzt dessen Schreibrechte.

Die Kacheln zeigen den letzten Wert im gewählten Zeitraum (standardmäßig fünf
Minuten), sonst „Keine Messdaten“. Der MQTT-Testsender erzeugt ausdrücklich simulierte Messwerte. Einrichtung: [Mac-MQTT-Test](../docs/mqtt-mac-test.md).

## Dashboard-Anordnung

Oben bleiben Geräte gesamt, Online und Offline. Darunter stehen die vier Messwertanzeigen in einer Reihe, jeweils mit zwei Nachkommastellen. Direkt darunter zeigt eine zweite Reihe die vier zugehörigen Messwertkurven. Ganz unten bleiben Geräteanzahl und Ping-Latenz nebeneinander. Alle Abfragen sind auf `.124` gefiltert.
