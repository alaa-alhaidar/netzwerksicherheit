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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scanner.sensor_registry import register_sensors
from scanner.sensor_config import load_sensor_targets, save_sensor_targets
from scanner.temperature_alarm import read_temperature, temperature_in_alarm

try:
    from .stats_view import StatisticsDialog
except ImportError:
    from stats_view import StatisticsDialog

from PyQt6.QtCore import QProcess, QSettings, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QListWidget, QListWidgetItem, QDoubleSpinBox, QScrollArea, QSpinBox,
    QStackedWidget, QVBoxLayout, QHBoxLayout, QWidget,
)

GRAFANA_URL = "https://breezycaribou3208.grafana.net/d/alxjsgs/sensor-124-e28093-umweltmonitor?from=now-5m&to=now&timezone=browser&refresh=5s"
TOLERANCE_STATE = Path("/home/alaa/pi-control/tolerance.json")


STYLE = """
QWidget { color: #243247; font: 14px 'DejaVu Sans'; }
QMainWindow, QDialog { background: #ffffff; }
QLabel { background: transparent; }
QLabel#title { font-size: 28px; font-weight: bold; color: #17243a; }
QLabel#muted { color: #62748a; }
QWidget#toolbar { background: #f4f7fb; border: 1px solid #dce4ee; border-radius: 12px; }
QLabel#summary { background: #edf8f5; border: 1px solid #c9e9de; border-radius: 10px;
    padding: 14px 18px; color: #176a57; font-weight: bold; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #ffffff; border: 1px solid #cad5e3;
    border-radius: 8px; padding: 10px; selection-background-color: #d7eee8; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #16836c; }
QComboBox QAbstractItemView { background: #f7f9fc; color: #243247;
    selection-background-color: #dbeafe; border: 1px solid #cad5e3; }
QPushButton { background: #e8eef5; border: 1px solid #cad5e3;
    border-radius: 8px; padding: 11px 18px; font-weight: bold; }
QPushButton:hover { background: #dde6f0; border-color: #a4b5ca; }
QPushButton:pressed { background: #d3dfea; }
QPushButton#startServices:enabled { background: #087f68; color: #ffffff; border-color: #087f68; }
QPushButton#startServices:enabled:hover { background: #096b59; border-color: #096b59; }
QPushButton#startServices:enabled:pressed { background: #075647; }
QPushButton#stopServices:enabled { background: #b91c1c; color: #ffffff; border-color: #b91c1c; }
QPushButton#stopServices:enabled:hover { background: #991b1b; border-color: #991b1b; }
QPushButton#stopServices:enabled:pressed { background: #7f1d1d; }
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
    return style + "QPushButton#startServices:enabled, QPushButton#stopServices:enabled { color: #ffffff; }"


def status_color(online, theme):
    if theme == "dark":
        return QColor("#4ade80" if online else "#f87171")
    return QColor("#16a34a" if online else "#dc2626")


class AppearanceDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.resize(540, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Darstellung")
        title.setObjectName("title")
        layout.addWidget(title)
        form = QFormLayout()
        self.device_rows = []
        self.device_list = QWidget()
        self.device_layout = QVBoxLayout(self.device_list)
        self.device_layout.setContentsMargins(0, 0, 0, 0)
        self.device_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for ip, name in parent.sensor_targets.items():
            self.add_device_row(ip, name)
        if not self.device_rows:
            self.add_device_row()
        device_scroll = QScrollArea()
        device_scroll.setWidgetResizable(True)
        device_scroll.setMinimumHeight(150)
        device_scroll.setMaximumHeight(260)
        device_scroll.setWidget(self.device_list)
        self.device_scroll = device_scroll
        form.addRow(QLabel("Geräte · Name und IPv4-Adresse"))
        form.addRow(device_scroll)
        add_device = QPushButton("+ Gerät hinzufügen")
        add_device.clicked.connect(lambda: self.add_device_row())
        form.addRow(add_device)
        save_sensor = QPushButton("Geräte speichern")
        save_sensor.clicked.connect(self.save_sensor)
        form.addRow(save_sensor)
        self.sensor_message = QLabel()
        self.sensor_message.setWordWrap(True)
        form.addRow(self.sensor_message)
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
        self.led_enabled = QCheckBox("LED bei kritischem Alarm blinken lassen")
        self.led_enabled.setChecked(parent.settings.value("hardware/led_enabled", False, type=bool))
        form.addRow("Hardware-Alarm", self.led_enabled)
        self.led_status = QLabel(parent.hardware_status())
        self.led_status.setWordWrap(True)
        form.addRow("LED-Status", self.led_status)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(lambda: self.led_status.setText(parent.hardware_status()))
        self.status_timer.start(2000)
        ranges = parent.load_alarm_ranges()
        range_title = QLabel("Zulässige Sensorbereiche")
        range_title.setStyleSheet("font-weight: bold; margin-top: 12px;")
        form.addRow(range_title)
        self.range_inputs = {}
        range_specs = (
            ("temperature_c", "Temperatur", " °C", -100, 200, 1),
            ("pressure_hpa", "Luftdruck", " hPa", 100, 1500, 1),
            ("humidity_pct", "Luftfeuchtigkeit", " %", 0, 100, 1),
            ("gas_resistance_ohm", "Luftqualität", " kΩ", 0, 1_000_000, 2),
        )
        for key, caption, suffix, minimum, maximum, decimals in range_specs:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            lower = QDoubleSpinBox()
            upper = QDoubleSpinBox()
            for field in (lower, upper):
                field.setRange(minimum, maximum)
                field.setDecimals(decimals)
                field.setSuffix(suffix)
            factor = 1000 if key == "gas_resistance_ohm" else 1
            lower.setValue(ranges[key]["min"] / factor)
            upper.setValue(ranges[key]["max"] / factor)
            row_layout.addWidget(QLabel("Von"))
            row_layout.addWidget(lower)
            row_layout.addWidget(QLabel("Bis"))
            row_layout.addWidget(upper)
            form.addRow(caption, row)
            self.range_inputs[key] = (lower, upper, factor)
        save_ranges = QPushButton("Zulässige Bereiche speichern")
        save_ranges.clicked.connect(self.save_ranges)
        form.addRow(save_ranges)
        self.range_message = QLabel()
        self.range_message.setWordWrap(True)
        form.addRow(self.range_message)
        layout.addLayout(form)
        self.view.currentIndexChanged.connect(self.apply)
        self.theme.currentIndexChanged.connect(self.apply)
        self.led_enabled.toggled.connect(self.apply_led)
        note = QLabel("Änderungen werden sofort angewendet und gespeichert.")
        note.setWordWrap(True)
        layout.addWidget(note)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        layout.addWidget(close)

    def apply(self):
        self.parent().apply_appearance(self.view.currentData(), self.theme.currentData())

    def apply_led(self):
        self.parent().apply_led(self.led_enabled.isChecked())

    def add_device_row(self, ip="", name=""):
        row = QWidget()
        fields = QHBoxLayout(row)
        fields.setContentsMargins(0, 0, 0, 0)
        name_input = QLineEdit(name)
        name_input.setPlaceholderText("Gerätename")
        name_input.setAccessibleName("Gerätename")
        ip_input = QLineEdit(ip)
        ip_input.setPlaceholderText("192.168.178.…")
        ip_input.setAccessibleName("IPv4-Adresse")
        remove = QPushButton("−")
        remove.setFixedWidth(44)
        remove.setStyleSheet("padding: 6px;")
        remove.setToolTip("Gerät aus der Liste entfernen; danach Geräte speichern")
        remove.setAccessibleName("Gerät entfernen")
        entry = (row, ip_input, name_input)
        remove.clicked.connect(lambda: self.remove_device_row(entry))
        fields.addWidget(name_input)
        fields.addWidget(ip_input)
        fields.addWidget(remove)
        self.device_rows.append(entry)
        self.device_layout.addWidget(row)
        if not ip:
            name_input.setFocus()
        if hasattr(self, "device_scroll"):
            QTimer.singleShot(0, lambda: self.device_scroll.ensureWidgetVisible(row)
                              if any(entry[0] is row for entry in self.device_rows) else None)

    def remove_device_row(self, entry):
        self.device_rows.remove(entry)
        self.device_layout.removeWidget(entry[0])
        entry[0].deleteLater()

    def save_sensor(self):
        targets = [(ip.text().strip(), name.text().strip()) for _, ip, name in self.device_rows
                   if ip.text().strip() or name.text().strip()]
        try:
            self.parent().set_sensors(targets)
        except (ValueError, sqlite3.Error) as exc:
            self.sensor_message.setText(str(exc))
            return
        self.sensor_message.setText(f"{len(targets)} Geräte gespeichert. Der Scanner übernimmt die Liste beim nächsten Durchlauf.")

    def save_ranges(self):
        values = {
            key: {"min": lower.value() * factor, "max": upper.value() * factor}
            for key, (lower, upper, factor) in self.range_inputs.items()
        }
        try:
            self.parent().save_alarm_ranges(values)
        except (ValueError, OSError, TypeError) as exc:
            self.range_message.setText(str(exc))
            return
        self.range_message.setText(
            "Bereiche gespeichert. Die automatische Alarmprüfung verwendet sie sofort."
        )



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
    if value == "1970-01-01T00:00:00+00:00":
        return "Noch keine Antwort"
    try:
        return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


def connection_info(device):
    try:
        info = json.loads(device.get("connection_info") or "{}")
        return info if isinstance(info, dict) else {}
    except (ValueError, TypeError):
        return {}


class ConnectionDialog(QDialog):
    def __init__(self, device, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Anschlussdetails · " + device["ip"])
        self.resize(540, 540)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        title = QLabel("Netzwerkanschluss")
        title.setObjectName("title")
        layout.addWidget(title)
        card = QWidget()
        card.setObjectName("toolbar")
        form = QFormLayout(card)
        form.setContentsMargins(20, 20, 20, 20)
        form.setVerticalSpacing(14)
        self.labels = {}
        for key, caption in [("target", "Gerät"), ("type", "Netztyp"),
                             ("interface", "Pi-Schnittstelle"), ("local_ip", "Lokale IP"),
                             ("network", "Lokales Netz"), ("gateway", "Gateway zum Gerät"),
                             ("mac", "Lokale MAC"), ("state", "Anschlussstatus"),
                             ("mtu", "MTU"), ("checked", "Ermittelt")]:
            label = QLabel()
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.labels[key] = label
            form.addRow(caption + ":", label)
        layout.addWidget(card)
        note = QLabel("Zeigt den Anschluss des Pi zum Gerät. Die Verbindung des Geräts "
                      "selbst (WLAN oder Kabel) ist damit nicht bestimmt. "
                      "Bei Offline-Geräten können die Angaben aus einem älteren Scan stammen.")
        note.setWordWrap(True)
        layout.addWidget(note)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.update_device(device)

    def update_device(self, device):
        info = connection_info(device)
        info["target"] = device["ip"]
        for key, label in self.labels.items():
            value = info.get(key)
            if key == "checked" and value:
                value = local_time(value)
            elif key == "gateway" and info.get("interface") and not value:
                value = "Direkt verbunden"
            label.setText(str(value) if value else "Unbekannt")


class MonitorWindow(QMainWindow):
    def __init__(self, db_path, interval=10, network="auto", scan_interval=60):
        super().__init__()
        self.db_path = str(Path(db_path).resolve())
        self.devices = []
        self.settings = QSettings(str(Path(self.db_path).parent / "ui-settings.ini"), QSettings.Format.IniFormat)
        self.sensor_targets = load_sensor_targets(self.settings)
        self.target_ip, self.sensor_name = next(iter(self.sensor_targets.items()), ("", ""))
        register_sensors(self.db_path, list(self.sensor_targets.items()))
        self.view_mode = self.settings.value("appearance/view", "list")
        self.theme_mode = self.settings.value("appearance/theme", "light")
        self.appearance_window = None
        self.card_buttons = {}
        self.detail_windows = {}
        self.connection_windows = {}
        self.offline_alerted = set()
        self.offline_popups = {}
        self.statistics_window = None
        self.network_override = network
        self.service_process = QProcess(self)
        self.service_process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.service_process.finished.connect(self.services_finished)
        self.service_process.errorOccurred.connect(self.services_error)
        self.service_action = None
        self.service_button_state = (True, True)
        self.pending_service_action = None
        self.closing = False
        self.service_output = ""
        self.service_process.readyReadStandardOutput.connect(self.services_output)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("Sensor-Monitor · Raspberry Pi 5")
        self.resize(1400, 680)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        title = QLabel("Sensor-Monitor")
        title.setObjectName("title")
        heading = QHBoxLayout()
        heading.addWidget(title)
        self.scan_indicator = QLabel("●")
        self.scan_indicator.setFixedWidth(24)
        heading.addWidget(self.scan_indicator)
        heading.addStretch()
        layout.addLayout(heading)
        self.blink_on = False
        subtitle = QLabel("Konfigurierte Geräte · Gerät anklicken für Details")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        scan_controls = QHBoxLayout(toolbar)
        scan_controls.setContentsMargins(16, 14, 16, 14)
        scan_controls.setSpacing(12)
        self.start_services_button = QPushButton("Dienste starten")
        self.start_services_button.setObjectName("startServices")
        self.start_services_button.clicked.connect(lambda: self.control_services("start"))
        scan_controls.addWidget(self.start_services_button)
        self.stop_services_button = QPushButton("Dienste stoppen")
        self.stop_services_button.setObjectName("stopServices")
        self.stop_services_button.clicked.connect(lambda: self.control_services("stop"))
        scan_controls.addWidget(self.stop_services_button)
        self.stats_button = QPushButton("Statistik")
        self.stats_button.clicked.connect(self.open_statistics)
        scan_controls.addWidget(self.stats_button)
        self.grafana_button = QPushButton("Grafana")
        self.grafana_button.clicked.connect(self.open_grafana)
        scan_controls.addWidget(self.grafana_button)
        self.settings_button = QPushButton("Einstellungen")
        self.settings_button.clicked.connect(self.open_settings)
        scan_controls.addWidget(self.settings_button)
        self.network_label = QLabel("Geräte: " + (", ".join(self.sensor_targets) or "noch nicht eingerichtet"))
        self.network_label.setMinimumWidth(180)
        self.network_label.setObjectName("muted")
        scan_controls.addWidget(self.network_label)
        scan_controls.addWidget(QLabel("Scanpause"))
        self.scan_interval = QSpinBox()
        self.scan_interval.setRange(1, 86400)
        self.scan_interval.setSuffix(" s")
        self.scan_interval.setValue(self.settings.value("scanner/interval", scan_interval, type=int))
        self.scan_interval.valueChanged.connect(self.save_scan_interval)
        self.scan_interval.setToolTip("Wird beim nächsten Klick auf Dienste starten übernommen.")
        scan_controls.addWidget(self.scan_interval)
        layout.addWidget(toolbar)
        self.service_status = QLabel("Dienstestatus wird geprüft …")
        self.service_status.setWordWrap(True)
        self.service_status.setObjectName("muted")
        layout.addWidget(self.service_status)
        self.service_error = QLabel()
        self.service_error.setWordWrap(True)
        layout.addWidget(self.service_error)
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "IP-Adresse", "Status", "Zuletzt erreichbar", "Zuletzt geprüft",
            "Hostname", "MAC", "Ping", "Kritisch", "Netztyp (Pi)",
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
        self.alarm_timer = QTimer(self)
        self.alarm_timer.setInterval(1000)
        self.alarm_timer.timeout.connect(self.check_critical_devices)
        self.alarm_timer.start()
        self.service_timer = QTimer(self)
        self.service_timer.timeout.connect(lambda: self.control_services("status"))
        self.service_timer.start(5000)
        QTimer.singleShot(0, lambda: self.control_services("status"))

    def apply_led(self, enabled):
        self.settings.setValue("hardware/led_enabled", enabled)
        self.settings.sync()

    def save_scan_interval(self, interval):
        self.settings.setValue("scanner/interval", interval)
        self.settings.sync()

    def load_alarm_ranges(self):
        fallback = {
            "temperature_c": {"min": 20.0, "max": 26.0},
            "pressure_hpa": {"min": 950.0, "max": 1050.0},
            "humidity_pct": {"min": 35.0, "max": 65.0},
            "gas_resistance_ohm": {"min": 50_000.0, "max": 200_000.0},
        }
        try:
            state = json.loads(TOLERANCE_STATE.read_text(encoding="utf-8"))
            ranges = state.get("ranges")
            if not isinstance(ranges, dict):
                return fallback
            for key in fallback:
                limits = ranges.get(key)
                if (not isinstance(limits, dict)
                        or not isinstance(limits.get("min"), (int, float))
                        or not isinstance(limits.get("max"), (int, float))
                        or limits["min"] >= limits["max"]):
                    return fallback
            return ranges
        except (OSError, ValueError, TypeError):
            return fallback

    def save_alarm_ranges(self, ranges):
        bounds = {
            "temperature_c": (-100.0, 200.0),
            "pressure_hpa": (100.0, 1500.0),
            "humidity_pct": (0.0, 100.0),
            "gas_resistance_ohm": (0.0, 1_000_000_000.0),
        }
        cleaned = {}
        for key, (lowest, highest) in bounds.items():
            limits = ranges.get(key, {})
            minimum, maximum = limits.get("min"), limits.get("max")
            if minimum is None or maximum is None or minimum >= maximum:
                raise ValueError(f"Minimum muss kleiner als Maximum sein ({key}).")
            if minimum < lowest or maximum > highest:
                raise ValueError(f"Bereich für {key} liegt außerhalb der erlaubten Grenzen.")
            cleaned[key] = {"min": float(minimum), "max": float(maximum)}
        try:
            state = json.loads(TOLERANCE_STATE.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                state = {}
        except (OSError, ValueError, TypeError):
            state = {}
        state["ranges"] = cleaned
        state["updated_at"] = datetime.now().astimezone().isoformat()
        TOLERANCE_STATE.parent.mkdir(parents=True, exist_ok=True)
        temporary = TOLERANCE_STATE.with_suffix(".gui.tmp")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        temporary.replace(TOLERANCE_STATE)

    def set_sensor(self, ip, name, camera_ip="", camera_name="ESP32-CAM"):
        self.set_sensors([(address, label) for address, label in [(ip, name), (camera_ip, camera_name)] if address])

    def set_sensors(self, targets):
        if self.service_action in ("start", "stop"):
            raise ValueError("Bitte warten, bis die Dienstesteuerung abgeschlossen ist.")
        targets = [(ip.strip(), name.strip() or "Sensor") for ip, name in targets]
        register_sensors(self.db_path, targets)
        for dialog in list(self.detail_windows.values()) + list(self.connection_windows.values()):
            dialog.close()
        self.sensor_targets = dict(targets)
        self.target_ip, self.sensor_name = next(iter(self.sensor_targets.items()), ("", ""))
        save_sensor_targets(self.settings, self.sensor_targets)
        self.network_label.setText("Geräte: " + (", ".join(self.sensor_targets) or "noch nicht eingerichtet"))
        self.refresh()
        if self.statistics_window is not None:
            self.statistics_window.refresh()

    def update_scan_indicator(self):
        color = status_color(True, self.theme_mode).name() if self.blink_on else ("#405570" if self.theme_mode == "dark" else "#cad5e3")
        self.scan_indicator.setStyleSheet(f"font-size: 20px; color: {color};")
        self.scan_indicator.setToolTip("Hintergrunddienste aktiv" if self.blink_on else "Dienste gestoppt oder unvollständig")

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
        if column == 8:
            self.open_connection_by_ip(item.text())
        else:
            self.open_device_by_ip(item.text())

    def open_connection_by_ip(self, ip):
        device = next((device for device in self.devices if device["ip"] == ip), None)
        if device is None:
            return
        dialog = self.connection_windows.get(ip)
        if dialog is None:
            dialog = ConnectionDialog(device, self)
            self.connection_windows[ip] = dialog
            dialog.finished.connect(lambda result, ip=ip: self.connection_windows.pop(ip, None))
        else:
            dialog.update_device(device)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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
        return self.settings.value(f"devices/{ip}/critical", ip in getattr(self, "sensor_targets", {self.target_ip: ""}), type=bool)

    def set_critical(self, ip, critical):
        self.settings.setValue(f"devices/{ip}/critical", bool(critical))
        self.settings.sync()
        self.render()
        self.check_critical_devices()

    def check_critical_devices(self, repeat=False):
        offline = {}
        reasons = {}
        try:
            reading = read_temperature(self.db_path, self.target_ip)
        except (sqlite3.Error, OSError):
            # A failed read does not clear an active temperature alarm.
            reading = getattr(self, "last_temperature", None)
        else:
            self.last_temperature = reading
        alarm_devices = list(self.devices)
        if reading is not None and not any(device["ip"] == self.target_ip for device in alarm_devices):
            alarm_devices.append({"ip": self.target_ip, "hostname": getattr(self, "sensor_name", "Sensor"),
                                  "online": True, "ping": ""})
        for device in alarm_devices:
            ip = device["ip"]
            if not self.is_critical(ip):
                continue
            causes = []
            if not device["online"] or device.get("ping") == "keine Antwort":
                causes.append("Sensor antwortet nicht (WLAN/Netzwerk).")
            if ip == self.target_ip and temperature_in_alarm(reading):
                causes.append(f"Temperatur {reading[0]:.1f} °C im Alarmbereich 41–45 °C.")
            if causes:
                offline[ip] = device
                reasons[ip] = "\n".join(causes)
            # Update open warnings when a second cause appears or one cause clears.
        for ip, popup in self.offline_popups.items():
            if ip in reasons:
                popup.setInformativeText(reasons[ip])
        for ip in list(self.offline_popups):
            if ip not in offline:
                self.offline_popups[ip].close()
        self.offline_alerted.intersection_update(offline)
        if repeat:
            self.offline_alerted.clear()
        for ip, device in offline.items():
            if ip in self.offline_alerted:
                continue
            self.offline_alerted.add(ip)
            if ip in self.offline_popups:
                popup = self.offline_popups[ip]
                popup.showNormal()
                popup.raise_()
                popup.activateWindow()
                continue
            popup = QMessageBox(self)
            popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            popup.setWindowTitle("Kritischer Sensoralarm")
            popup.setIcon(QMessageBox.Icon.Warning)
            popup.setTextFormat(Qt.TextFormat.PlainText)
            name = device.get("hostname") or "Unbekanntes Gerät"
            popup.setText(f"Alarm für das kritische Gerät {name} ({ip}).")
            popup.setInformativeText(reasons[ip])
            popup.setStandardButtons(QMessageBox.StandardButton.Ok)
            popup.setWindowModality(Qt.WindowModality.NonModal)
            self.offline_popups[ip] = popup
            popup.finished.connect(lambda result, ip=ip: self.offline_popups.pop(ip, None))
            popup.show()
            popup.raise_()
            popup.activateWindow()

    def hardware_status(self):
        try:
            state = json.loads((Path(self.db_path).parent / "hardware-status.json").read_text())
            return state.get("alarm", "Hardwaredienst wartet auf Daten")
        except (OSError, ValueError, AttributeError):
            return "Hardwaredienst nicht aktiv oder noch keine Daten"

    def control_services(self, action):
        if self.closing:
            return
        if self.service_process.state() != QProcess.ProcessState.NotRunning:
            if self.service_action == "status" and action != "status":
                self.pending_service_action = action
            return
        if action == "start" and not self.sensor_targets:
            self.message.setText("Unter Einstellungen zuerst die Sensor-IP eintragen.")
            self.open_settings()
            return
        self.service_action = action
        self.service_output = ""
        if action != "status":
            self.service_error.clear()
            self.start_services_button.setEnabled(False)
            self.stop_services_button.setEnabled(False)
            self.scan_interval.setEnabled(False)
            self.message.setText("Dienste werden gestartet …" if action == "start" else "Dienste werden gestoppt …")
        script = Path(__file__).resolve().parents[1] / "scripts/control-services.py"
        self.service_process.start(sys.executable, [str(script), action, "--db", self.db_path,
                                  "--target", self.target_ip, "--interval", str(self.scan_interval.value())])

    def services_output(self):
        self.service_output += bytes(self.service_process.readAllStandardOutput()).decode(errors="replace")

    def services_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.service_status.setText("Dienstesteuerung konnte nicht gestartet werden: " + self.service_process.errorString())
            self.finish_service_controls()

    def finish_service_controls(self):
        start_enabled, stop_enabled = self.service_button_state
        self.start_services_button.setEnabled(start_enabled)
        self.stop_services_button.setEnabled(stop_enabled)
        self.scan_interval.setEnabled(True)
        self.service_action = None

    def services_finished(self, exit_code, exit_status):
        self.services_output()
        action = self.service_action
        try:
            result = json.loads(self.service_output)
            if exit_code or "error" in result:
                raise ValueError(result.get("error", "Dienstesteuerung fehlgeschlagen"))
            if action == "status":
                states = result["services"]
                active = all(value == "running" for value in states.values()) and result["hardware"] == "active"
                stopped_states = {"stopped", "exited", "dead", "inactive", "failed", "not-found"}
                stopped = all(value in stopped_states for value in states.values()) and result["hardware"] in stopped_states
                self.service_button_state = (not active, not stopped)
                self.blink_on = active
                self.update_scan_indicator()
                labels = {"scanner": "Scanner", "mqtt": "MQTT", "telemetry": "Sensordaten", "sync": "Synchronisierung", "postgres": "Datenbank", "pdc": "Grafana-Verbindung"}
                text = [labels[name] + ": " + ("läuft" if state == "running" else "gestoppt (" + state + ")") for name, state in states.items()]
                text.append("LED-Steuerung: " + ("läuft" if result["hardware"] == "active" else result["hardware"]))
                self.service_status.setText(" · ".join(text))
            else:
                # Wait for the follow-up status before enabling another action.
                self.service_button_state = (False, False)
                self.message.setText(result["message"])
        except (ValueError, KeyError, TypeError) as exc:
            self.service_button_state = (True, True)
            self.service_status.setText("Dienstefehler: " + str(exc))
            self.blink_on = False
            self.update_scan_indicator()
            if action != "status":
                self.service_error.setText("Dienstefehler: " + str(exc))
                self.message.setText("Aktion nicht vollständig abgeschlossen. Details siehe Dienstestatus.")
        self.finish_service_controls()
        pending = self.pending_service_action
        self.pending_service_action = None
        if pending or action != "status":
            QTimer.singleShot(0, lambda: self.control_services(pending or "status"))

    def closeEvent(self, event):
        if self.service_action in ("start", "stop"):
            self.message.setText("Dienstesteuerung läuft noch. Fenster danach schließen.")
            event.ignore()
            return
        self.service_timer.stop()
        self.closing = True
        self.pending_service_action = None
        if self.service_process.state() != QProcess.ProcessState.NotRunning:
            self.service_process.kill()
            self.service_process.waitForFinished(1000)
        event.accept()
        if self.appearance_window is not None:
            self.appearance_window.close()
        if self.statistics_window is not None:
            self.statistics_window.close()
        for dialog in list(self.detail_windows.values()):
            dialog.close()
        for dialog in list(self.connection_windows.values()):
            dialog.close()
        for popup in list(self.offline_popups.values()):
            popup.close()

    def refresh(self):
        try:
            devices = read_devices(self.db_path)
        except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
            self.message.setText("Laden fehlgeschlagen; Anzeige enthält alte Daten: " + str(exc))
            return
        devices = [device for device in devices if device["ip"] in self.sensor_targets]
        for device in devices:
            device["hostname"] = self.sensor_targets[device["ip"]]
        self.devices = devices
        for device in devices:
            dialog = self.detail_windows.get(device["ip"])
            if dialog is not None:
                dialog.update_device(device)
            connection = self.connection_windows.get(device["ip"])
            if connection is not None:
                connection.update_device(device)
        self.render()
        self.check_critical_devices()
        if self.service_action in ("start", "stop"):
            return
        if not devices:
            self.message.setText("Sensor noch nicht geprüft. Dienste starten." if self.target_ip else
                                 "Unter Einstellungen die IP-Adresse von alaa mac eintragen.")
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
                      "★ Kritisch" if self.is_critical(device["ip"]) else "—",
                      connection_info(device).get("type") or "Unbekannt"]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, bool(device["online"]))
                item.setToolTip(value)
                if column == 8:
                    item.setToolTip("Anschlussdetails des Pi öffnen")
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
            kind = connection_info(device).get("type") or "Netztyp unbekannt"
            button.setText(f"{name}\n{device['ip']} · {kind}\n\n{status}   ·   Ping: {device.get('ping') or '—'}\n{device.get('mac') or 'MAC unbekannt'}")
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
                                    if key not in dict(self.FIELDS) and key not in ("detail_error", "connection_info")]
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
        connection = QPushButton("Anschlussdetails")
        connection.clicked.connect(lambda: parent.open_connection_by_ip(device["ip"]))
        buttons.addWidget(connection)
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
