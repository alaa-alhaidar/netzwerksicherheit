# Mac → MQTT auf dem Pi → PostgreSQL → Grafana

Der Mac erzeugt zunächst **simulierte** Temperatur-, Luftdruck-, Feuchtigkeits-
und Gaswiderstandswerte. Nmap liefert weiterhin ausschließlich Netzwerkstatus
und Ping für 192.168.178.124. MQTT-Messwerte ändern diese Scan-Ergebnisse nicht.

## Auf dem Pi

Im Projektverzeichnis die Tabelle anlegen beziehungsweise erweitern:

```bash
sudo docker exec -i network-postgres psql -v ON_ERROR_STOP=1 -U networkuser -d networkdb < docker/postgres/sensor-measurements.sql
sudo docker compose -f docker/compose-cloud.yaml up -d --build mqtt telemetry
```

Falls hier nur `docker-compose` installiert ist, `docker compose` durch
`docker-compose` ersetzen. Der Empfänger nutzt die vorhandenen PostgreSQL-
Zugangsdaten in `docker/.env.cloud`. Diese Datei bleibt auf dem Pi.

## Auf dem Mac

Das Projekt auf den Mac kopieren (ohne die privaten `.env`-Dateien). Python 3
und SSH werden benötigt. Im ersten Terminal einen Tunnel öffnen; `PI-BENUTZER`
und `PI-IP` durch die tatsächlichen Pi-Zugangsdaten ersetzen:

```bash
ssh -N -L 1883:127.0.0.1:1883 PI-BENUTZER@PI-IP
```

Im zweiten Terminal im Projektverzeichnis:

```bash
python3 -m venv .venv-mqtt
source .venv-mqtt/bin/activate
python3 -m pip install -r scanner/requirements-mqtt.txt
python3 scripts/mac_fake_sensor.py
```

Der Sender veröffentlicht alle fünf Sekunden auf
`iot/v1/nodes/lab-01/telemetry`, QoS 1, ohne retained-Nachricht. Mit `--once`
wird eine Nachricht gesendet. `Ctrl+C` beendet den Sender. Der SSH-Tunnel
muss währenddessen offen bleiben; der Broker ist am Pi nur auf 127.0.0.1
veröffentlicht. Der lokale Testbroker erlaubt anonyme Verbindungen hinter
SSH; er ist nicht für eine direkte Veröffentlichung im LAN eingerichtet.

## Überprüfen

```bash
sudo docker compose -f docker/compose-cloud.yaml logs --tail=20 telemetry
sudo docker exec network-postgres psql -U networkuser -d networkdb -c "SELECT received_at,source,temperature_c,pressure_hpa,humidity_pct,gas_resistance_ohm FROM sensor_measurements ORDER BY received_at DESC,id DESC LIMIT 5;"
```

Das aktualisierte `grafana/network-monitor-dashboard.json` importieren und
„Letzte 5 Minuten“ wählen. Die vier Kacheln zeigen die simulierten Messwerte.
Nach Ende des Sendens verschwinden die Werte aus diesem Zeitfenster.

## Später der echte Sensor

Der Sensor ersetzt den Mac-Sender, behält Topic, `node_id`, `boot_id`,
`sequence` und die vier Felder im Nachrichtenvertrag bei und setzt
`source` auf `sensor`. `boot_id` muss pro Neustart neu sein, `sequence` pro
Nachricht steigen. Der Empfänger ordnet `lab-01` über `SENSOR_IP` der im
Dashboard verwendeten Adresse `.124` zu; das ist eine Konfiguration und
keine Erkennung der Absender-IP. Zum Wechsel den Mac-Sender stoppen.

Für den ESP32 ist vor dem direkten LAN-Zugriff ein MQTT-Listener mit TLS,
Benutzeranmeldung und Topic-Berechtigungen einzurichten. Die Python-Clients
unterstützen `MQTT_USERNAME`, `MQTT_PASSWORD` und `MQTT_CA_FILE`. Der bestehende
lokale SSH-Test stellt noch keinen ESP32-Zugang bereit. Die Speicherung
verwendet die Empfangszeit des Pi; doppelte Nachrichten mit gleicher
Knoten-, Boot- und Sequenzkennung werden ignoriert. Der MQTT-Empfänger
bestätigt Nachrichten erst nach erfolgreichem Datenbank-Commit.

Die Client-Anbindung verwendet die [offizielle Paho-MQTT-API](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html).

## Schreibfehler wegen fehlender Rechte

`ON CONFLICT (node_id,boot_id,sequence)` benötigt SELECT auf diesen drei Spalten.
Die aktualisierte SQL-Datei gewährt diese Rechte zusätzlich zu INSERT. Bei einer
bereits eingerichteten Tabelle die SQL-Datei erneut ausführen. Anschließend
`telemetry` neu starten. Bei anderen Fehlern zeigt die aktualisierte Version
Fehlerklasse und SQLSTATE an, ohne Zugangsdaten zu protokollieren.
