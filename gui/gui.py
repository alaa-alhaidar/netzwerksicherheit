#!/usr/bin/env python3
"""Qt-Desktopoberfläche für den Netzwerk-Monitor."""
import argparse
from datetime import datetime
import ipaddress
import json
import os
import re
from pathlib import Path
import sqlite3
import sys

try:
    from .stats_view import StatisticsDialog
except ImportError:
    from stats_view import StatisticsDialog

from PyQt6.QtCore import QProcess, QSettings, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QHBoxLayout, QWidget,
)

GRAFANA_URL = "https://breezycaribou3208.grafana.net/d/almljvn/netzwerkueberwachung-e28093-pi-5?from=now-5m&to=now&timezone=browser&refresh=5s"

STYLE = """
QWidget { color: #243247; font: 14px 'DejaVu Sans'; }
QMainWindow, QDialog { background: #ffffff; }
QLabel { background: transparent; }
QLabel#title { font-size: 28px; font-weight: bold; color: #17243a; }
QLabel#muted { color: #62748a; }
QWidget#toolbar { background: #f4f7fb; border: 1px solid #dce4ee; border-radius: 12px; }
QLabel#summary { background: #edf8f5; border: 1px solid #c9e9de; border-radius: 10px;
    padding: 14px 18px; color: #176a57; font-weight: bold; }
QLineEdit, QSpinBox, QComboBox { background: #ffffff; border: 1px solid #cad5e3;
    border-radius: 8px; padding: 10px; selection-background-color: #d7eee8; }
QLineEdit:focus, QSpinBox:focus { border: 1px solid #16836c; }
QComboBox QAbstractItemView { background: #f7f9fc; color: #243247;
    selection-background-color: #dbeafe; border: 1px solid #cad5e3; }
QPushButton { background: #e8eef5; border: 1px solid #cad5e3;
    border-radius: 8px; padding: 11px 18px; font-weight: bold; }
QPushButton:hover { background: #dde6f0; border-color: #a4b5ca; }
QPushButton:pressed { background: #d3dfea; }
QPushButton#scan { background: #087f68; color: #ffffff; border-color: #087f68; }
QPushButton#scan:hover { background: #096b59; border-color: #096b59; }
QPushButton#scan:pressed { background: #075647; }
QPushButton:disabled { background: #edf1f6; color: #8190a3; border-color: #dce4ee; }
QTableWidget { background: #ffffff; alternate-background-color: #f7f9fc;
    border: 1px solid #dce4ee; border-radius: 12px; gridline-color: #e8eef5;
    selection-background-color: #dbeafe; selection-color: #17243a; }
QTableWidget::item { padding: 10px 12px; border-bottom: 1px solid #e8eef5; }
QHeaderView::section { background: #edf2f8; color: #4b6078; border: none;
    padding: 14px 12px; font-weight: bold; }
QTableCornerButton::section { background: #edf2f8; border: none; }
QScrollArea { background: #ffffff; border: 1px solid #dce4ee; border-radius: 10px; }
QScrollArea > QWidget > QWidget { background: #ffffff; }
QScrollBar:vertical { background: #ffffff; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #b6c5d7; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #e8eef5; color: #17243a; border: 1px solid #cad5e3; padding: 6px; }
"""

STYLE += """
QListWidget { background: #ffffff; border: 1px solid #dce4ee; border-radius: 12px; padding: 8px; }
QListWidget::item { background: transparent; border: none; }
QPushButton#deviceCard { background: #f4f7fb; color: #243247; border: 1px solid #cad5e3;
    text-align: left; padding: 18px; border-radius: 12px; font-weight: normal; }
QPushButton#deviceCard:hover { background: #edf8f5; border-color: #16836c; }
QPushButton#deviceCard[online="true"] { border: 2px solid #16a34a; }
QPushButton#deviceCard[online="false"] { border: 2px solid #dc2626; }
"""


def theme_style(mode):
    if mode == "light":
        return STYLE
    colors = {
        "#243247": "#dce6f0", "#ffffff": "#111d2e", "#17243a": "#f5f9ff",
        "#62748a": "#a3b5ca", "#f4f7fb": "#162235", "#dce4ee": "#34445c",
        "#edf8f5": "#142f32", "#c9e9de": "#285c55", "#176a57": "#94e5d6",
        "#cad5e3": "#405570", "#d7eee8": "#276e71", "#16836c": "#57debf",
        "#f7f9fc": "#162337", "#dbeafe": "#254f64", "#e8eef5": "#23344b",
        "#dde6f0": "#30465f", "#a4b5ca": "#6a819d", "#d3dfea": "#182639",
        "#edf1f6": "#1a293d", "#8190a3": "#7f92ac", "#edf2f8": "#1e2d43",
        "#4b6078": "#aebfd3", "#e1e9f2": "#1e3044", "#b6c5d7": "#405570",
        "#16a34a": "#4ade80", "#dc2626": "#f87171",
    }
    style = re.sub(r"#[0-9a-f]{6}", lambda match: colors.get(match.group(), match.group()), STYLE)
    return style + "QPushButton#scan { color: #ffffff; }"


def status_color(online, theme):
    if theme == "dark":
        return QColor("#4ade80" if online else "#f87171")
    return QColor("#16a34a" if online else "#dc2626")


class AppearanceDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.resize(430, 240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Darstellung")
        title.setObjectName("title")
        layout.addWidget(title)
        form = QFormLayout()
        self.view = QComboBox()
        self.view.addItem("Liste", "list")
        self.view.addItem("Karten", "cards")
        self.view.setCurrentIndex(self.view.findData(parent.view_mode))
        form.addRow("Geräteansicht", self.view)
        self.theme = QComboBox()
        self.theme.addItem("Hell", "light")
        self.theme.addItem("Dunkel", "dark")
        self.theme.setCurrentIndex(self.theme.findData(parent.theme_mode))
        form.addRow("Farbschema", self.theme)
        layout.addLayout(form)
        self.view.currentIndexChanged.connect(self.apply)
        self.theme.currentIndexChanged.connect(self.apply)
        note = QLabel("Änderungen werden sofort angewendet und gespeichert.")
        note.setWordWrap(True)
        layout.addWidget(note)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        layout.addWidget(close)

    def apply(self):
        self.parent().apply_appearance(self.view.currentData(), self.theme.currentData())



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
        self.settings = QSettings(str(Path(self.db_path).parent / "ui-settings.ini"), QSettings.Format.IniFormat)
        self.view_mode = self.settings.value("appearance/view", "list")
        self.theme_mode = self.settings.value("appearance/theme", "light")
        self.appearance_window = None
        self.card_buttons = {}
        self.detail_windows = {}
        self.offline_alerted = set()
        self.offline_popups = {}
        self.statistics_window = None
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
        heading = QHBoxLayout()
        heading.addWidget(title)
        self.scan_indicator = QLabel("●")
        self.scan_indicator.setFixedWidth(24)
        heading.addWidget(self.scan_indicator)
        heading.addStretch()
        layout.addLayout(heading)
        self.blink_on = False
        self.blink_timer = QTimer(self)
        self.blink_timer.setInterval(450)
        self.blink_timer.timeout.connect(self.blink_scan_indicator)
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
        button = QPushButton("Aktualisieren")
        button.clicked.connect(self.refresh)
        scan_controls.addWidget(button)
        self.stats_button = QPushButton("Statistik")
        self.stats_button.clicked.connect(self.open_statistics)
        scan_controls.addWidget(self.stats_button)
        self.grafana_button = QPushButton("Grafana")
        self.grafana_button.clicked.connect(self.open_grafana)
        scan_controls.addWidget(self.grafana_button)
        self.settings_button = QPushButton("Einstellungen")
        self.settings_button.clicked.connect(self.open_settings)
        scan_controls.addWidget(self.settings_button)
        self.network_label = QLabel("Netz: automatische Erkennung")
        self.network_label.setMinimumWidth(180)
        self.network_label.setObjectName("muted")
        scan_controls.addWidget(self.network_label)
        scan_controls.addWidget(QLabel("Scanpause"))
        self.scan_interval = QSpinBox()
        self.scan_interval.setRange(1, 86400)
        self.scan_interval.setSuffix(" s")
        self.scan_interval.setValue(scan_interval)
        scan_controls.addWidget(self.scan_interval)
        layout.addWidget(toolbar)
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([
            "IP-Adresse", "Status", "Zuletzt erreichbar", "Zuletzt geprüft",
            "Hostname", "MAC", "Ping", "Kritisch",
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
        self.cards = QListWidget()
        self.cards.setViewMode(QListWidget.ViewMode.IconMode)
        self.cards.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.cards.setMovement(QListWidget.Movement.Static)
        self.cards.setWrapping(True)
        self.cards.setSpacing(10)
        self.cards.setGridSize(QSize(310, 190))
        self.views = QStackedWidget()
        self.views.addWidget(self.table)
        self.views.addWidget(self.cards)
        layout.addWidget(self.views)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        layout.addWidget(self.message)
        self.setCentralWidget(container)
        self.timer = QTimer(self)
        self.refresh_interval = interval * 1000
        self.timer.timeout.connect(self.refresh)
        self.timer.start(interval * 1000)
        self.apply_appearance(self.view_mode, self.theme_mode)
        self.refresh()

    def update_scan_indicator(self):
        color = status_color(True, self.theme_mode).name() if self.blink_on else ("#405570" if self.theme_mode == "dark" else "#cad5e3")
        self.scan_indicator.setStyleSheet(f"font-size: 20px; color: {color};")
        self.scan_indicator.setToolTip("Scan läuft" if self.blink_timer.isActive() else "Kein Scan aktiv")

    def blink_scan_indicator(self):
        self.blink_on = not self.blink_on
        self.update_scan_indicator()

    def open_settings(self):
        if self.appearance_window is None:
            self.appearance_window = AppearanceDialog(self)
        self.appearance_window.show()
        self.appearance_window.raise_()
        self.appearance_window.activateWindow()

    def apply_appearance(self, view, theme):
        self.view_mode = view if view in ("list", "cards") else "list"
        self.theme_mode = theme if theme in ("light", "dark") else "light"
        self.settings.setValue("appearance/view", self.view_mode)
        self.settings.setValue("appearance/theme", self.theme_mode)
        self.settings.sync()
        self.setStyleSheet(theme_style(self.theme_mode))
        self.update_scan_indicator()
        self.views.setCurrentIndex(1 if self.view_mode == "cards" else 0)
        self.render()
        if self.statistics_window is not None:
            self.statistics_window.update()
            self.statistics_window.online_chart.update()
            self.statistics_window.ping_chart.update()

    def open_grafana(self):
        if not QDesktopServices.openUrl(QUrl(GRAFANA_URL)):
            self.message.setText("Grafana konnte nicht im Browser geöffnet werden.")

    def open_statistics(self):
        if self.statistics_window is None:
            self.statistics_window = StatisticsDialog(self.db_path, self)
        self.statistics_window.show()
        self.statistics_window.raise_()
        self.statistics_window.activateWindow()

    def open_device_details(self, row, column):
        item = self.table.item(row, 0)
        if item is None:
            return
        self.open_device_by_ip(item.text())

    def open_device_by_ip(self, ip):
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

    def is_critical(self, ip):
        return self.settings.value(f"devices/{ip}/critical", False, type=bool)

    def set_critical(self, ip, critical):
        self.settings.setValue(f"devices/{ip}/critical", bool(critical))
        self.settings.sync()
        self.render()
        self.check_critical_devices()

    def check_critical_devices(self):
        offline = {device["ip"]: device for device in self.devices
                   if self.is_critical(device["ip"]) and not device["online"]}
        for ip in list(self.offline_popups):
            if ip not in offline:
                self.offline_popups[ip].close()
        self.offline_alerted.intersection_update(offline)
        for ip, device in offline.items():
            if ip in self.offline_alerted:
                continue
            self.offline_alerted.add(ip)
            popup = QMessageBox(self)
            popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            popup.setWindowTitle("Kritisches Gerät offline")
            popup.setIcon(QMessageBox.Icon.Warning)
            popup.setTextFormat(Qt.TextFormat.PlainText)
            name = device.get("hostname") or "Unbekanntes Gerät"
            popup.setText(f"Das kritische Gerät {name} ({ip}) ist offline.")
            popup.setInformativeText("Das Gerät wurde beim letzten Scan nicht erreicht.")
            popup.setStandardButtons(QMessageBox.StandardButton.Ok)
            popup.setWindowModality(Qt.WindowModality.NonModal)
            self.offline_popups[ip] = popup
            popup.finished.connect(lambda result, ip=ip: self.offline_popups.pop(ip, None))
            popup.show()
            popup.raise_()
            popup.activateWindow()

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
        self.blink_timer.start()
        self.blink_on = True
        self.update_scan_indicator()
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
        self.blink_timer.stop()
        self.blink_on = False
        self.update_scan_indicator()
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
        self.blink_timer.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            self.message.setText("Scanner wird beendet … Fenster danach erneut schließen.")
            QTimer.singleShot(1500, self.stop_scan)
            event.ignore()
            return
        event.accept()
        if self.appearance_window is not None:
            self.appearance_window.close()
        if self.statistics_window is not None:
            self.statistics_window.close()
        for dialog in list(self.detail_windows.values()):
            dialog.close()
        for popup in list(self.offline_popups.values()):
            popup.close()

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
        self.check_critical_devices()
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
            values = [device["ip"], "● Online" if device["online"] else "● Offline",
                      local_time(device["last_seen"]), local_time(device["last_checked"]),
                      device.get("hostname") or "unbekannt", device.get("mac") or "unbekannt",
                      device.get("ping") or "unbekannt",
                      "★ Kritisch" if self.is_critical(device["ip"]) else "—"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, bool(device["online"]))
                item.setToolTip(value)
                if column == 1:
                    item.setForeground(status_color(device["online"], self.theme_mode))
                self.table.setItem(row, column, item)

        identities = [device["ip"] for device in devices]
        if list(self.card_buttons) != identities:
            self.cards.clear()
            self.card_buttons = {}
            for device in devices:
                ip = device["ip"]
                item = QListWidgetItem(self.cards)
                item.setSizeHint(QSize(300, 180))
                button = QPushButton()
                button.setObjectName("deviceCard")
                button.clicked.connect(lambda checked=False, ip=ip: self.open_device_by_ip(ip))
                self.cards.setItemWidget(item, button)
                self.card_buttons[ip] = button
        for device in devices:
            button = self.card_buttons[device["ip"]]
            online = bool(device["online"])
            if button.property("online") != online:
                button.setProperty("online", online)
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
            name = device.get("hostname") or "Unbekanntes Gerät"
            name = button.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, 260)
            status = "● Online" if device["online"] else "○ Offline"
            if self.is_critical(device["ip"]):
                status += " · ★ Kritisch"
            button.setText(f"{name}\n{device['ip']}\n\n{status}   ·   Ping: {device.get('ping') or '—'}\n{device.get('mac') or 'MAC unbekannt'}")
            button.setToolTip("Gerätedetails öffnen: " + device["ip"])


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
        self.critical_checkbox = QCheckBox("Als kritisches Gerät markieren")
        self.critical_checkbox.setChecked(parent.is_critical(device["ip"]))
        self.critical_checkbox.setToolTip("Die Markierung wird sofort für dieses Gerät gespeichert.")
        self.critical_checkbox.toggled.connect(
            lambda checked: parent.set_critical(device["ip"], checked))
        form.addRow("Überwachung:", self.critical_checkbox)
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
        self.port_process.start(sys.executable, [str(script), "--ports-ip", device["ip"],
                                               "--db", parent.db_path])

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
