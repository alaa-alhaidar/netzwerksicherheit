# ESP32-S3-N16R8 / OV2640

Basis: Espressif Arduino-ESP32 3.3.12, Beispiel CameraWebServer.
Quelle: https://github.com/espressif/arduino-esp32/tree/3.3.12/libraries/ESP32/examples/Camera/CameraWebServer

Pinprofil: CAMERA_MODEL_ESP32S3_EYE (für diese Boardfamilie vorgesehen;
Kameraerkennung muss am angeschlossenen Board geprüft werden).
Build: ESP32S3 Dev Module, Flash 16 MB, PSRAM OPI, Partition Huge APP, USB CDC an.
Serielle Diagnose wird alle fünf Sekunden ausgegeben; WLAN wird auch bei
fehlgeschlagener Kameraprobe verbunden.

WLAN-Zugangsdaten werden nur lokal in einer ignorierten Datei
`wifi_credentials.h` eingesetzt. Keine Zugangsdaten ins Git einchecken.
Der Webserver ist für das Heimnetz bestimmt; es wird keine Portfreigabe angelegt.
Nach dem Start meldet die serielle Ausgabe die Kamera-IP (115200 Baud).

Das Urheberrecht der übernommenen Beispiel-Dateien liegt bei Espressif.

## Stand der Prüfung am angeschlossenen Board

ESP32-S3, MAC 28:84:85:49:38:00, 16 MB Flash und 8 MB PSRAM wurden ausgelesen.
WLAN-Verbindung erfolgreich; zugewiesene Adresse: 192.168.178.135.
Der Kameratreiber meldet noch `0x106 / ESP_ERR_NOT_SUPPORTED` bei der Probe.
Ein Bildstream ist damit noch nicht funktionsfähig. Das Kameramodul ist derzeit noch nicht angeschlossen (vom Benutzer bestätigt).
Bis zur Montage wird nur die Netzwerkverbindung überwacht; Bildausgabe und
Kamerapinbelegung werden nach Anschluss des Moduls geprüft.
Die ursprüngliche Firmware ist unter `data/camera-backups/` gesichert.
