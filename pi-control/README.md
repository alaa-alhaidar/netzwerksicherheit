# Lokale PWA-Steuerungs-API

Diese API läuft auf dem Pi als `pi-control-api.service` und steuert über
`scripts/control-services.py` dieselben Dienste wie die Qt-Oberfläche.
Die vorhandene Installation verwendet `/home/alaa/pi-control/pi_control_api.py`;
die Quelle wird hier ohne Zugangsdaten versioniert.

Die Umgebungsvariable `PI_CONTROL_TOKEN` ist erforderlich und wird aus der
vorhandenen lokalen Dienstkonfiguration geladen. Sie gehört nicht ins Git.
Das Pi-WLAN, die Token-Konfiguration und der HTTPS-Tunnel bleiben lokale
Installationseinstellungen. Nach Übernahme der API-Datei den Benutzerdienst
mit `systemctl --user restart pi-control-api.service` neu starten.
