# Sensor-Monitor für Raspberry Pi 5

Die geplante Umstellung zum modularen IoT-Prototyp ist in der
[IoT-Systemarchitektur](docs/iot-architektur.md) beschrieben. Sie enthält das
Gesamtdiagramm, Modulgrenzen und den gemeinsamen Vertrag für Fake-Sensor und ESP32.
Die folgende Anleitung beschreibt den vorhandenen Netzwerk-Monitor.

Die native Qt-Oberfläche überwacht genau einen Sensor mit konfigurierter IP-Adresse.
Unter „Einstellungen“ werden Sensor-IP und Anzeigename gespeichert. Nmap und Ping
prüfen nur diesen Sensor; Popups, GPIO-LED und lokale Statistik beziehen sich auf
seine Erreichbarkeit. Aktueller Laborknoten: „alaa mac“, `192.168.178.124`.

Der separate Scanner unterstützt weiterhin komplette IPv4-Netzbereiche für
Diagnosezwecke. MQTT-Messwerte und PWA sind noch nicht implementiert.

```text
scanner/netz_monitor.py   Netzwerk-Scanner
gui/gui.py               Qt-Desktopoberfläche (PyQt6)
gui/requirements.txt     Python-Abhängigkeiten
docker/compose.yaml      Scanner als Docker-Dienst
scripts/start.sh         Docker-Scanner starten
scripts/start-gui.sh     Desktopoberfläche starten
```

## Installation auf dem Pi

Die Oberfläche benötigt eine laufende Desktopsitzung, Python 3.10+ und PyQt6.
Unter Raspberry Pi OS:

```bash
sudo apt update
sudo apt install python3-pyqt6 nmap iputils-ping iproute2
git clone https://github.com/alaa-alhaidar/netzwerksicherheit.git ~/network-monitor
cd ~/network-monitor
```

Alternativ PyQt6 in einer virtuellen Umgebung installieren:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r gui/requirements.txt
```

[PyQt6-Installationsanleitung](https://www.riverbankcomputing.com/software/pyqt/download)

## Oberfläche starten und per Button scannen

In der Pi-Desktopsitzung im Projektverzeichnis:

```bash
bash scripts/start-gui.sh
```

Unter Einstellungen die Sensor-IP hinterlegen und **Dienste starten** drücken.
Der Button startet Scanner, MQTT, Telemetrie, PostgreSQL und Synchronisierung
über Docker Compose sowie die LED-Steuerung als systemd-Benutzerdienst.
Docker Compose, die vorhandenen Cloud-Konfigurationsdateien und eine aktive
systemd-Benutzersitzung sind erforderlich. Der Benutzer benötigt Docker- und GPIO-Zugriff.
Der erste Start baut die Container und kann einige Minuten dauern.

Die GUI liest die Datenbank und zeigt den Dienstestatus alle fünf Sekunden an.
**Fenster schließen beendet keine Hintergrunddienste.** **Dienste stoppen** beendet
die genannten Dienste einschließlich der LEDs; gespeicherte Daten bleiben erhalten.
PWA und GUI verwenden dieselbe Dienstesteuerung (`scripts/control-services.py`).
PWA-Start startet auch den Scanner; PWA-Stopp stoppt ihn und schaltet die
LED-Ausgänge aus. Der gemeinsame Status berücksichtigt den Scanner.
Sensor-IP und Scanpause werden aus `data/ui-settings.ini` übernommen.
Gleichzeitige Start-/Stopp-Befehle werden nacheinander ausgeführt.
Öffnen der GUI startet keine Dienste automatisch. Die Scanpause (Standard: 60 Sekunden)
wird bei „Dienste starten“ übernommen. Nach einem Sensorwechsel die Dienste stoppen
und erneut starten. Die Hintergrunddienste verwenden `monitor.sqlite3` im gewählten
Datenverzeichnis. Bei installierten PWA-Benutzerdiensten werden `pi-mqtt`, `pi-telemetry` und
`pi-alarm` sowie die PDC-Verbindung ebenfalls gestartet und gestoppt. Dabei
werden kein zweiter MQTT-Broker und keine zweite GPIO-Steuerung gestartet.
PWA und Steuerungs-API bleiben erreichbar; gespeicherte letzte Werte können
weiterhin angezeigt werden, erhalten nach dem Stopp aber keine neuen Messungen.

Die LED-Pins stehen in `gui/hardware_service.py` (`ALARM_LED_PIN = 17`,
`CONNECTION_LED_PIN = 22`). Der Hardwaredienst läuft ohne sichtbares Fenster.
Logs: `journalctl --user -u network-monitor-hardware.service`.
Der Benutzerdienst überlebt das Schließen der GUI; ein Neustart des Pi oder
vollständiges Abmelden benötigt einen erneuten Start des Hardwaredienstes.

Ein Klick auf eine Gerätezeile öffnet ein eigenes Detailfenster mit IP, Status,
Hostname, MAC, Ping, Diensten, erster Erkennung, letzter Erreichbarkeit, letzter
Prüfung. Die Metadaten lassen sich markieren oder mit
„Metadaten kopieren“ vollständig kopieren. Offene Detailfenster aktualisieren
sich mit der Geräteliste, auch wenn das Gerät inzwischen offline ist.

Ein separater Scanner ist für diesen Button nicht erforderlich. Nmap, ping und
ip müssen direkt auf dem Pi installiert sein. Ein Docker-Scanner ist optional;
für manuelle Button-Scans sollte der Dauer-Scanner gestoppt werden, damit sich
beide Scans nicht überschneiden. Root-Rechte werden von der Oberfläche nicht
automatisch angefordert; Nmap läuft mit den Rechten des Desktopbenutzers.

Ein Fehler wird angezeigt; die Wiederholungen laufen weiter. Während eines
laufenden Scans beendet ein Schließen-Versuch den Scanner; danach das Fenster
nochmals schließen. `bash scripts/start-gui.sh --network 192.168.1.0/24` setzt
einen optionalen manuellen Netzbereich. Standardmäßig ist `--network auto` aktiv.

Optional den Scanner separat im Terminal starten:

```bash
python3 scanner/netz_monitor.py --network 192.168.178.0/24
```

`--once` führt einen einzelnen Scan aus; `--interval 60` legt die Pause zwischen
Scans fest. Bei einem anderen Datenbankpfad beide Programme mit
`--db /pfad/monitor.sqlite3` starten. `bash scripts/start-gui.sh --refresh 5`
aktualisiert die Ansicht alle fünf Sekunden; während Button-Scans häufiger.

## Scanner mit Docker starten

Voraussetzung: Docker Engine und Docker Compose Plugin auf dem Linux-Pi.

```bash
cp docker/.env.example docker/.env
nano docker/.env
bash scripts/start.sh
bash scripts/start-gui.sh
```

In `docker/.env` ist `NETWORK_CIDR=auto` voreingestellt.
Compose startet den Scanner; die Qt-Oberfläche läuft direkt in der Desktopsitzung
und liest dieselbe Datenbank unter `data/`. Falls der frühere Webcontainer läuft,
diesen einmal entfernen:

```bash
docker compose --env-file docker/.env -f docker/compose.yaml up -d --build --remove-orphans
```

```bash
docker compose --env-file docker/.env -f docker/compose.yaml logs -f
docker compose --env-file docker/.env -f docker/compose.yaml down
```

Der Scanner startet nach einem Neustart automatisch, sofern Docker beim Booten
startet. Die Oberfläche wird manuell gestartet. Daten bleiben bei `down`
erhalten. Die Netzbereiche werden vor jedem Scan neu ermittelt.

## Grenzen und Datensicherung

Geräte, die Nmaps Erkennungsproben blockieren, können als offline erscheinen. Unbekannte,
unerreichbare Adressen werden nicht gespeichert. Nach einem Scannerstopp bleiben
die letzten Statuswerte bestehen. Herstellererkennung und Benachrichtigungen sind noch nicht enthalten.

Für eine Datenbanksicherung den Scanner stoppen und das gesamte Verzeichnis
`data/` kopieren. Datenbank und lokale Konfiguration sind von Git ausgeschlossen.
Codeänderungen committen und pushen.

## Nmap-Befehl zuerst ausführen

Den Netzbereich an das eigene LAN anpassen:

```bash
sudo nmap -sn 192.168.178.0/24
python3 scanner/netz_monitor.py --network 192.168.178.0/24 --once
bash scripts/start-gui.sh
```

Der erste Befehl zeigt erkannte Geräte im Terminal. Der zweite führt den gesamten
Scanner aus und speichert die Ergebnisse für Qt. Intern verwendet er zuerst
`nmap -sn <Netzbereich>`. Erst nach dieser Geräteerkennung werden für jedes
gefundene Gerät Hostname, MAC-Adresse aus `ip neigh`, Ping-Latenz und die zehn
konfigurierten TCP-Ports abgefragt:

```text
22 SSH       53 DNS       80 HTTP      443 HTTPS    445 SMB
554 RTSP     1883 MQTT    3389 RDP     5000 HTTP/API 8080 HTTP-ALT
```

Der Portbefehl lautet `nmap -Pn -p 22,53,80,443,445,554,1883,3389,5000,8080 --open <IP>`.
Die Dienstnamen sind feste Portzuordnungen, keine bestätigte Diensterkennung.
DNS-Port 53 wird hier nur über TCP geprüft. MAC-Adressen sind normalerweise nur
für Geräte im direkt angeschlossenen Netz verfügbar. Hostname und MAC können
„unbekannt“ bleiben. Der Scanner gibt alle Informationen auch im Terminal aus.

Mit Root-Rechten kann Nmap im lokalen Ethernet ARP verwenden; ohne Root können
die Erkennungsresultate abweichen. Einmaliger Scan mit Root, danach Qt starten:

```bash
mkdir -p data
sudo python3 scanner/netz_monitor.py --network 192.168.178.0/24 --once
sudo chown -R "$(id -u):$(id -g)" data
bash scripts/start-gui.sh
```

Die Datenbank wird automatisch um die Metadatenfelder erweitert; bestehende
Geräte bleiben erhalten. Alle erkannten Geräte werden vor der Detailabfrage
gespeichert, damit sie sofort in Qt erscheinen. Die Details folgen Gerät für
Gerät. Fehlgeschlagene Portabfragen werden als Fehler angezeigt und nicht als
„keine Ports offen“ behandelt. Offline-Geräte behalten ihre zuletzt erfassten
Metadaten; die Spalte „Zuletzt erreichbar“ zeigt deren Alter.

Eine fehlgeschlagene oder unvollständige Geräteerkennung verändert die
Gerätestatus nicht. Bei `--once` endet sie mit einem Fehlercode. Im Dauerbetrieb
wird nach dem Intervall erneut versucht. `--timeout 300` setzt das Zeitlimit pro
Nmap-Aufruf; DNS-Auflösung verwendet die Zeitlimits des Systemresolvers.

[Nmap-Geräteerkennung](https://nmap.org/book/man-host-discovery.html)

`--scan-interval 30` setzt die Pause zwischen Scans auf 30 Sekunden.

## Automatische Netzwerkerkennung

Ethernet und WLAN werden anhand ihrer aktiven IPv4-Adressen und Netzmasken erkannt.
Mehrere lokale Netze werden gescannt, doppelte Netzbereiche zusammengeführt.
Loopback, Docker-/virtuelle Bridge- und übliche VPN-Interfaces werden ausgelassen.
Ohne aktives Netz erscheint eine Fehlermeldung; der Dauerbetrieb versucht es nach
seiner Pause erneut. Beim Netzwechsel werden früher bekannte Geräte nach der
nächsten erfolgreichen Geräteerkennung als offline markiert.
IPv6 und Netze mit mehr als 4096 Adressen werden nicht automatisch gescannt.
Für große Netze kann mit `--network <CIDR>` ein Teilbereich festgelegt werden.

## Dienste erst beim Öffnen

Der regelmäßige Netzwerkscan fragt Hostname, MAC und Ping ab. Portscans laufen
erst beim Klick auf ein Gerät im Hintergrund. Dienste erscheinen ausschließlich
im Detailfenster. Währenddessen steht dort „Dienste werden abgefragt …“.
Beim erneuten Öffnen werden die Dienste neu geprüft; Schließen beendet die Abfrage.
# network-monitor-

## Statistik

Der Button **Statistik** öffnet ein eigenes Fenster mit:

- aktuellen Zahlen für bekannte, online und offline gemeldete Geräte;
- zuletzt gefundenen offenen TCP-Diensten und Zeitpunkt der Abfrage;
- Verlauf der erreichbaren Geräte und des durchschnittlichen Pings pro Scan;
- Erreichbarkeitsquote und durchschnittlichem Ping je Gerät.

Der Zeitraum ist wählbar: eine Stunde, 24 Stunden, sieben oder 30 Tage.
Kurven zeigen höchstens die letzten 400 Scans im Zeitraum; die Gerätetabelle
wertet alle gespeicherten Messungen des Zeitraums aus. Aktualisierung alle fünf
Sekunden. Die aktuellen Geräte- und Dienstzahlen sind vom Zeitraum unabhängig.
Dienste werden weiterhin ausschließlich beim Klick auf ein Gerät gescannt;
die Statistik verwendet die letzte erfolgreiche gespeicherte Abfrage.

Verlaufsdaten entstehen erst ab dem ersten Scan dieser Version; alte Werte
werden nicht nachträglich erfunden. Bestehende Datenbanken werden automatisch
erweitert. Fehlgeschlagene Geräteerkennung erzeugt keine Messungen. Nur Geräte
in tatsächlich gescannten Netzen gehen in die Erreichbarkeitsquote ein. Die Quote
ist ein Anteil von Erkennungen, keine zeitbasierte Uptime. Fehlende Pingantworten
und obere Grenzen wie `<1 ms` werden nicht in Pingdurchschnitte einbezogen.
Die Historie bleibt in SQLite erhalten und wächst mit der Zahl der Scans.

## Grafana

Der Button **Grafana** öffnet das konfigurierte Dashboard im Standardbrowser:
[Netzwerküberwachung](https://breezycaribou3208.grafana.net/d/almljvn/netzwerkueberwachung-e28093-pi-5?from=now-5m&to=now&timezone=browser&refresh=5s).
Der Link verwendet die letzten fünf Minuten und aktualisiert alle fünf Sekunden.
Eine Grafana-Anmeldung kann erforderlich sein. Dieser Button überträgt keine
Scanner-Messwerte an Grafana; dafür muss eine Datenquelle eingerichtet werden.

## Grafana Cloud und bestehendes PostgreSQL

Die erhaltene Datenbank `networkdb` kann jetzt für Grafana Cloud verwendet werden.
Die lokale Synchronisierung und PDC-Konfiguration stehen in
[dieser Anleitung](grafana/README.md). Cloud-Zugangsdaten bleiben lokal.

## Darstellung einstellen

Über **Einstellungen** in der oberen Button-Leiste:

- **Geräteansicht:** Liste oder Karten. Beide zeigen alle bekannten Geräte;
  ein Klick auf eine Karte öffnet dieselben Gerätedetails wie eine Tabellenzeile.
- **Farbschema:** Hell oder Dunkel. Das gilt auch für Einstellungen,
  Gerätedetails und Statistik einschließlich der Diagramme.

Die Auswahl wird sofort angewendet und in `data/ui-settings.ini` gespeichert
(bei anderem Datenbankpfad daneben). Standard: helle Listenansicht. Beim nächsten
Start wird die zuletzt gespeicherte Darstellung geladen. Die Datei bleibt lokal.

### Kritische Geräte markieren

Im Detailfenster eines Geräts lässt sich „Als kritisches Gerät markieren“ aktivieren
oder entfernen. Die Änderung wird sofort gespeichert und in Liste und Karten als
„★ Kritisch“ angezeigt. Die Markierung bleibt nach einem Neustart erhalten und ist
an die IP-Adresse gebunden. Automatische Neustarts werden dadurch nicht ausgelöst.

Ist ein kritisches Gerät offline oder antwortet es auf den ersten Ping nicht,
erscheint sofort nach der Erkennung in der
Oberfläche ein Warn-Popup mit Hostname und IP-Adresse. Der Scan läuft dabei weiter.
Nach jedem erfolgreich abgeschlossenen Scan erscheint die Warnung erneut, solange
das Gerät offline bleibt oder keine Ping-Antwort liefert. Ein noch offenes Popup wird wieder in den Vordergrund
geholt; bereits bestätigte Warnungen werden erneut geöffnet. Auch beim Markieren eines bereits offline
angezeigten Geräts erscheint die Warnung. Das Popup schließt sich, wenn das Gerät
wieder erreichbar ist und auf Ping antwortet oder die Markierung entfernt wird.

Für Ping wird ein Versuch mit einer Antwortfrist von einer Sekunde verwendet
(`ping -c 1 -W 1`). Auch Geräte, die Nmap als online erkennt, lösen bei fehlender
Ping-Antwort die Warnung aus. Geräte, die ICMP blockieren, können daher ebenfalls
gemeldet werden. Es gibt keine zusätzliche Wartezeit über mehrere Fehlversuche.

### Netztyp und Anschlussdetails

Die Spalte „Netztyp (Pi)“ zeigt WLAN, Ethernet oder einen unbekannten/virtuellen
Anschluss. Sie beschreibt die lokale Schnittstelle, über die der Pi das Gerät
laut Routingtabelle erreicht. Der Anschluss des entfernten Geräts selbst lässt
sich aus Nmap/Ping nicht zuverlässig bestimmen.

Ein Klick auf die Spalte öffnet eine Anschlusskarte mit Schnittstelle, lokaler IP,
Netzbereich, Gateway zum Gerät, lokaler MAC, Anschlussstatus, MTU und Zeit der
Ermittlung. In der Kartenansicht öffnet man zuerst das Gerät und anschließend
„Anschlussdetails“. Die Angaben werden beim Scan ermittelt und lokal gespeichert;
bei Offline-Geräten bleiben die letzten ermittelten Angaben sichtbar. Nach dem
Update ist für vorhandene Geräte ein neuer Scan nötig. Der PostgreSQL-Abgleich
überträgt weiterhin die bisherigen Geräte- und Statistikfelder.

### LED-Alarm am Pi 5 (ohne Buzzer)

Verdrahtung für eine LED: GPIO17 (physischer Pin 11) → 470-Ω-Vorwiderstand →
LED-Anode (+); LED-Kathode (−) → GND (physischer Pin 6).

Unter „Einstellungen“ die Option „LED bei kritischem Alarm blinken lassen“
aktivieren. Den Alarm-Pin direkt in `gui/hardware_service.py` ändern (BCM-Nummer,
nicht die physische Pinnummer). Die Option wird lokal gespeichert. Die grüne
Verbindungs-LED verwendet GPIO22 unabhängig von dieser Alarmoption.

Die LED blinkt mit 500 ms an / 500 ms aus, solange mindestens ein als kritisch
markiertes Gerät offline ist oder keine Ping-Antwort liefert. Das Bestätigen eines
Popups beendet nur die Bildschirmmeldung, nicht den LED-Alarm. Sobald alle
kritischen Geräte wieder antworten oder die Markierungen entfernt werden, geht
die LED aus. „Dienste stoppen“ gibt die GPIO-Ausgänge frei; Schließen der GUI lässt
die LED-Steuerung weiterlaufen. Auch MQTT-Temperaturen von 41–45 °C lösen den Alarm aus.

Die Ansteuerung läuft im Hintergrunddienst und verwendet GPIO Zero mit lgpio für
den Pi 5. Falls benötigt, auf dem Pi installieren:

```bash
sudo apt install python3-gpiozero python3-lgpio
```

Bei Nutzung einer virtuellen Python-Umgebung gibt es ergänzend
`gui/requirements-gpio.txt`. Der angemeldete Benutzer benötigt Zugriff auf die
GPIO-Geräte. Fehlt dieser Zugriff, zeigt „LED-Status“ in den Einstellungen den
Fehler an; Scans und Popups funktionieren weiterhin. Die Softwaretests verwenden
simulierte Ausgänge; die physische LED muss am Pi überprüft werden.

### Erste IoT-Umstellung: ein Sensor mit IP-Adresse

Die Pi-Oberfläche ist jetzt ein Sensor-Monitor. Unter „Einstellungen“ werden genau
eine Sensor-IP und ein Anzeigename hinterlegt; der vorgesehene erste Name ist
„alaa mac“. Ohne konfigurierte IP startet keine Netzwerksuche. Nur der ausgewählte
Sensor erscheint in Liste, Karten, lokaler Statistik und kritischen Alarmen.
Andere gespeicherte IP-Adressen bleiben als bisherige Daten erhalten, werden aber
in der Sensor-Oberfläche nicht berücksichtigt.

„Dienste starten“ prüft gezielt diese einzelne IP mit Nmap und Ping, statt den
Netzbereich nach weiteren Geräten abzusuchen. Ein noch nie erreichter Sensor zeigt
„Noch keine Antwort“ als letzte Erreichbarkeit. Nach einem Sensorwechsel die Dienste
stoppen und starten; die Auswahl bleibt nach einem Neustart erhalten.

Für die Kommandozeile:

```bash
python3 scanner/netz_monitor.py --target-ip <SENSOR-IP> --once
```

Der Docker-Scanner bleibt ein separat konfigurierbarer Netzwerk-Scanner. Nach der unten beschriebenen PostgreSQL-Umstellung enthält der
Grafana-Abgleich ebenfalls nur den manuell ausgewählten Sensor. MQTT-Messwerte und die PWA folgen als eigene Umsetzungsschritte.

### PostgreSQL-Abgleich für die IoT-Sensorüberwachung

Grafana bleibt an PostgreSQL angebunden. Der Exporter übernimmt nur manuell in der
Pi-Oberfläche eingetragene, aktivierte Sensoren und deren tatsächliche Prüfungen.
Aktuell ist das genau „alaa mac“ (`192.168.178.124`). Andere Netzwerkgeräte werden
nicht weiter nach PostgreSQL exportiert und aus dessen Monitor-Tabellen entfernt.
Das lokale SQLite-Archiv bleibt erhalten.

Einmal im Projektverzeichnis auf dem Pi ausführen:

```bash
bash scripts/apply-iot-sensors.sh
```

Dabei werden die Datenbankrechte angepasst und der aktualisierte Exporter gestartet.
Das vorhandene Grafana-Dashboard zählt dann die wirklichen Zeilen in PostgreSQL;
ein Import oder Wechsel der Datenquelle ist dafür nicht nötig. MQTT-Sensormesswerte
sind weiterhin ein späterer Schritt; aktuell sind die realen Daten Nmap-/Ping-Prüfungen.

### Zwei Geräte manuell eintragen

Unter **Einstellungen** können zwei Geräte mit jeweils eigener IPv4-Adresse und
eigenem Namen gespeichert werden, etwa Arduino Nano und ESP32-CAM. Ein leeres
zweites IP-Feld lässt weiterhin die Überwachung eines einzelnen Geräts zu.
Bereits gespeicherte IPs und Namen bleiben erhalten; doppelte und ungültige IPs
werden zurückgewiesen. Nach der Änderung **Dienste starten** drücken, damit
der Scanner mit der neuen Konfiguration gebaut und gestartet wird. Er liest
alle aktiv eingetragenen Geräte bei jedem Durchlauf aus `registered_sensors`.
Die GUI und ihre Statistik zeigen nur diese ausgewählten Geräte.

Unbekannte IP-Adressen findet man in der FRITZ!Box unter **Heimnetz → Netzwerk**.
Ein ESP32-Hostname allein unterscheidet einen Nano ESP32 nicht sicher von einer
ESP32-Kamera. Es werden keine Geräte-IP-Adressen automatisch zugeordnet.
