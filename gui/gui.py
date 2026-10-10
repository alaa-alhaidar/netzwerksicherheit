#!/usr/bin/env python3
"""Qt-Desktopoberfläche für den Netzwerk-Monitor."""
import argparse
from datetime import datetime
import ipaddress
import json
import os
from pathlib import Path
import sqlite3
import sys

from PyQt6.QtCore import QProcess, Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QDialog, QFormLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QPushButton, QTableWidget, QTableWidgetItem,
    QProgressBar, QScrollArea, QSpinBox, QVBoxLayout, QHBoxLayout, QWidget,
)

STYLE = """
QWidget { color: #dce6f0; font: 14px 'DejaVu Sans'; }
QMainWindow, QDialog { background: #0c1320; }
QLabel { background: transparent; }
QLabel#title { font-size: 28px; font-weight: bold; color: #f5f9ff; }
QLabel#muted { color: #91a4bc; }
QWidget#toolbar { background: #162235; border: 1px solid #28394f; border-radius: 12px; }
QLabel#summary { background: #142735; border: 1px solid #244451; border-radius: 10px;
    padding: 14px 18px; color: #94e5d6; font-weight: bold; }
QLineEdit, QSpinBox { background: #101c2d; border: 1px solid #384e68;
    border-radius: 8px; padding: 10px; selection-background-color: #276e71; }
QLineEdit:focus, QSpinBox:focus { border: 1px solid #4dd4bd; }
QPushButton { background: #23344b; border: 1px solid #384e68;
    border-radius: 8px; padding: 11px 18px; font-weight: bold; }
QPushButton:hover { background: #30465f; border-color: #6a819d; }
QPushButton:pressed { background: #182639; }
QPushButton#scan { background: #57debf; color: #092c2c; border-color: #57debf; }
QPushButton#scan:hover { background: #85ecd3; border-color: #85ecd3; }
QPushButton#scan:pressed { background: #32bfa1; }
QPushButton:disabled { background: #1a293d; color: #7f92ac; border-color: #28394f; }
QTableWidget { background: #111d2e; alternate-background-color: #162337;
    border: 1px solid #28394f; border-radius: 12px; gridline-color: #23344b;
    selection-background-color: #254f64; selection-color: #ffffff; }
QTableWidget::item { padding: 10px 12px; border-bottom: 1px solid #23344b; }
QHeaderView::section { background: #1e2d43; color: #aebfd3; border: none;
    padding: 14px 12px; font-weight: bold; }
QTableCornerButton::section { background: #1e2d43; border: none; }
QProgressBar { border: none; background: #1e3044; border-radius: 3px; }
QProgressBar::chunk { background: #57debf; border-radius: 3px; }
QScrollArea { background: #111d2e; border: 1px solid #28394f; border-radius: 10px; }
QScrollArea > QWidget > QWidget { background: #111d2e; }
QScrollBar:vertical { background: #111d2e; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #405570; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #23344b; color: #f5f9ff; border: 1px solid #536984; padding: 6px; }
"""



def read_devices(path):
    if not Path(path).is_file():
        return []
    with sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2) as db:
        db.row_factory = sqlite3.Row
        try:
            rows = [dict(row) for row in db.execute("SELECT * FROM devices")]
        except sqlite3.OperationalError as exc:
            if str(exc) == "no such table: devices":
                return []
            raise
    return sorted(rows, key=lambda row: ipaddress.IPv4Address(row["ip"]))



def local_time(value):
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


class MonitorWindow(QMainWindow):
    def __init__(self, db_path, interval=10, network="auto", scan_interval=60):
        super().__init__()
        self.db_path = str(Path(db_path).resolve())
        self.devices = []
        self.detail_windows = {}
        self.network_override = network
        self.scanning = False
        self.scan_timer = QTimer(self)
        self.scan_timer.setSingleShot(True)
        self.scan_timer.timeout.connect(self.start_scan)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.scan_output)
        self.process.finished.connect(self.scan_finished)
        self.process.errorOccurred.connect(self.scan_error)
        self.scan_log = ""
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Netzwerk-Monitor · Raspberry Pi 5")
        self.resize(1400, 680)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        title = QLabel("Netzwerk-Monitor")
        title.setObjectName("title")
        layout.addWidget(title)
        subtitle = QLabel("Dein Netzwerk im Blick · Geräte anklicken für Details")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        scan_controls = QHBoxLayout(toolbar)
        scan_controls.setContentsMargins(16, 14, 16, 14)
        scan_controls.setSpacing(12)
        self.scan_button = QPushButton("Scanning starten")
        self.scan_button.setObjectName("scan")
        self.scan_button.clicked.connect(self.toggle_scanning)
        scan_controls.addWidget(self.scan_button)
        button = QPushButton("Ansicht aktualisieren")
        button.clicked.connect(self.refresh)
        scan_controls.addWidget(button)
        self.network_label = QLabel("Netz: automatische Erkennung")
        self.network_label.setMinimumWidth(240)
        self.network_label.setObjectName("muted")
        scan_controls.addWidget(self.network_label)
        scan_controls.addWidget(QLabel("Pause (Sekunden)"))
        self.scan_interval = QSpinBox()
        self.scan_interval.setRange(1, 86400)
        self.scan_interval.setValue(scan_interval)
        scan_controls.addWidget(self.scan_interval)
        layout.addWidget(toolbar)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "IP-Adresse", "Status", "Zuletzt erreichbar", "Zuletzt geprüft",
            "Hostname", "MAC", "Ping",
        ])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self.open_device_details)
        self.table.setToolTip("Gerät anklicken, um alle Metadaten zu öffnen")
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        layout.addWidget(self.message)
        self.setCentralWidget(container)
        self.timer = QTimer(self)
        self.refresh_interval = interval * 1000
        self.timer.timeout.connect(self.refresh)
        self.timer.start(interval * 1000)
        self.refresh()

    def open_device_details(self, row, column):
        item = self.table.item(row, 0)
        if item is None:
            return
        ip = item.text()
        device = next((device for device in self.devices if device["ip"] == ip), None)
        if device is None:
            return
        dialog = self.detail_windows.get(ip)
        if dialog is None:
            dialog = DeviceDetailsDialog(device, self)
            self.detail_windows[ip] = dialog
            dialog.finished.connect(lambda result, ip=ip: self.detail_windows.pop(ip, None))
        else:
            dialog.update_device(device)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def toggle_scanning(self):
        if self.scanning:
            self.scanning = False
            self.scan_timer.stop()
            if self.process.state() != QProcess.ProcessState.NotRunning:
                self.process.terminate()
                self.scan_button.setEnabled(False)
                QTimer.singleShot(1500, self.stop_scan)
            else:
                self.reset_scan_controls()
            self.message.setText("Scanning gestoppt")
        else:
            self.start_scan()

    def schedule_scan(self):
        if self.scanning:
            self.scan_timer.start(self.scan_interval.value() * 1000)

    def start_scan(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.scanning = True
        self.scan_log = ""
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scanning stoppen")
        self.scan_interval.setEnabled(False)
        self.progress.setRange(0, 0)
        self.timer.setInterval(500)
        self.message.setText("Geräte werden mit Nmap gesucht …")
        script = Path(__file__).resolve().parents[1] / "scanner" / "netz_monitor.py"
        self.process.start(sys.executable, [str(script), "--network", self.network_override,
                                           "--db", self.db_path, "--once"])

    def scan_output(self):
        if not self.process.isOpen():
            return
        output = bytes(self.process.readAllStandardOutput()).decode(errors="replace")
        self.scan_log = (self.scan_log + output)[-8000:]
        for line in self.scan_log.splitlines():
            if line.startswith("Erkannte Netze: "):
                self.network_label.setText("Netz: " + line.removeprefix("Erkannte Netze: "))
        lines = output.strip().splitlines()
        if lines:
            self.message.setText(lines[-1])
        self.refresh()

    def reset_scan_controls(self):
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scanning stoppen" if self.scanning else "Scanning starten")
        self.scan_interval.setEnabled(not self.scanning)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.timer.setInterval(self.refresh_interval)

    def scan_finished(self, exit_code, exit_status):
        self.scan_output()
        self.reset_scan_controls()
        self.refresh()
        if not self.scanning:
            self.message.setText("Scanning gestoppt")
            return
        self.schedule_scan()
        if exit_code == 0 and exit_status == QProcess.ExitStatus.NormalExit:
            self.message.setText(f"Scan abgeschlossen · nächster Scan in {self.scan_interval.value()} Sekunden")
        else:
            self.message.setText("Scan fehlgeschlagen: " + (self.scan_log.strip().splitlines()[-1]
                                 if self.scan_log.strip() else "Scanner wurde beendet"))

    def scan_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.scanning = False
            self.scan_timer.stop()
            self.reset_scan_controls()
            self.message.setText("Scanner konnte nicht gestartet werden: " + self.process.errorString())

    def closeEvent(self, event):
        self.scanning = False
        self.scan_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            self.message.setText("Scanner wird beendet … Fenster danach erneut schließen.")
            QTimer.singleShot(1500, self.stop_scan)
            event.ignore()
            return
        event.accept()
        for dialog in list(self.detail_windows.values()):
            dialog.close()

    def stop_scan(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()

    def refresh(self):
        try:
            devices = read_devices(self.db_path)
        except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
            self.message.setText("Laden fehlgeschlagen; Anzeige enthält alte Daten: " + str(exc))
            return
        self.devices = devices
        for device in devices:
            dialog = self.detail_windows.get(device["ip"])
            if dialog is not None:
                dialog.update_device(device)
        self.render()
        if self.process.state() != QProcess.ProcessState.NotRunning or self.scanning:
            return
        if not devices:
            self.message.setText("Noch keine Geräte erkannt. Scanner, Netzbereich und Datenbankpfad prüfen.")
        else:
            self.message.setText("Ansicht aktualisiert: " + datetime.now().strftime("%H:%M:%S")
                                 + " · Status entspricht dem letzten Scan.")

    def render(self):
        devices = self.devices
        online = sum(bool(device["online"]) for device in self.devices)
        self.summary.setText(f"{len(self.devices)} bekannte Geräte · {online} online · "
                             f"{len(self.devices) - online} offline · {len(devices)} angezeigt")
        self.table.setRowCount(len(devices))
        for row, device in enumerate(devices):
            values = [device["ip"], "Online" if device["online"] else "Offline",
                      local_time(device["last_seen"]), local_time(device["last_checked"]),
                      device.get("hostname") or "unbekannt", device.get("mac") or "unbekannt",
                      device.get("ping") or "unbekannt"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 1:
                    item.setForeground(QColor("#70e5c1" if device["online"] else "#f5b580"))
                self.table.setItem(row, column, item)


class DeviceDetailsDialog(QDialog):
    FIELDS = [
        ("ip", "IP-Adresse"), ("online", "Status"), ("hostname", "Hostname"),
        ("mac", "MAC-Adresse"), ("ping", "Ping-Latenz"), ("services", "Dienste / offene TCP-Ports"),
        ("first_seen", "Erstmals erkannt"), ("last_seen", "Zuletzt erreichbar"),
        ("last_checked", "Zuletzt geprüft"),
    ]

    def __init__(self, device, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Gerätedetails · " + device["ip"])
        self.resize(680, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel("Gerätedetails")
        title.setObjectName("title")
        layout.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(20, 20, 20, 20)
        form.setVerticalSpacing(18)
        self.labels = {}
        self.fields = self.FIELDS + [(key, key) for key in device
                                    if key not in dict(self.FIELDS) and key != "detail_error"]
        for key, caption in self.fields:
            label = QLabel()
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.labels[key] = label
            form.addRow(caption + ":", label)
        scroll.setWidget(content)
        layout.addWidget(scroll)
        note = QLabel("Die Werte stammen aus dem letzten Scan und werden mit der Geräteliste aktualisiert.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        copy = QPushButton("Metadaten kopieren")
        copy.clicked.connect(self.copy_metadata)
        buttons.addWidget(copy)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.service_text = "Dienste werden abgefragt …"
        self.update_device(device)
        self.port_process = QProcess(self)
        self.port_process.finished.connect(self.ports_finished)
        self.port_process.errorOccurred.connect(self.ports_error)
        script = Path(__file__).resolve().parents[1] / "scanner" / "netz_monitor.py"
        self.port_process.start(sys.executable, [str(script), "--ports-ip", device["ip"]])

    def ports_finished(self, exit_code, exit_status):
        try:
            if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
                raise ValueError("Portscan fehlgeschlagen")
            data = json.loads(bytes(self.port_process.readAllStandardOutput()).decode())
            self.service_text = str(data["services"])
        except (ValueError, KeyError):
            self.service_text = "Dienste konnten nicht abgefragt werden"
        self.labels["services"].setText(self.service_text)

    def ports_error(self, error):
        self.service_text = "Dienste konnten nicht abgefragt werden"
        self.labels["services"].setText(self.service_text)

    def closeEvent(self, event):
        if self.port_process.state() != QProcess.ProcessState.NotRunning:
            self.port_process.terminate()
            if not self.port_process.waitForFinished(500):
                self.port_process.kill()
                self.port_process.waitForFinished(500)
        super().closeEvent(event)

    def update_device(self, device):
        for key, caption in self.fields:
            value = device.get(key)
            if key == "services":
                value = self.service_text
            elif key == "online":
                value = "Online" if value else "Offline"
            elif key in ("first_seen", "last_seen", "last_checked"):
                value = local_time(value) if value else "unbekannt"
            elif not value:
                value = "keine" if key == "detail_error" else "unbekannt"
            self.labels[key].setText(str(value))

    def copy_metadata(self):
        QApplication.clipboard().setText("\n".join(
            f"{caption}: {self.labels[key].text()}" for key, caption in self.fields))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default_db = Path(__file__).resolve().parents[1] / "data" / "monitor.sqlite3"
    parser.add_argument("--db", default=os.getenv("MONITOR_DB", str(default_db)))
    parser.add_argument("--refresh", type=int, default=10, help="Aktualisierung in Sekunden")
    parser.add_argument("--network", default=os.getenv("NETWORK_CIDR", "auto"))
    parser.add_argument("--scan-interval", type=int, default=5, help="Pause zwischen Scans in Sekunden")
    args = parser.parse_args()
    if not 1 <= args.scan_interval <= 86400:
        parser.error("--scan-interval muss zwischen 1 und 86400 liegen")
    if args.refresh < 1:
        parser.error("--refresh muss positiv sein")
    app = QApplication(sys.argv[:1])
    window = MonitorWindow(args.db, args.refresh, args.network, args.scan_interval)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
