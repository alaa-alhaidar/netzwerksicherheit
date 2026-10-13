"""Read-only statistics and Qt charts for recorded scanner measurements."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QHeaderView, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)


def load_statistics(path, hours, target_ip=None):
    empty = {"devices": [], "history": [], "availability": [], "services": []}
    if not Path(path).is_file():
        return empty
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=0.2) as db:
        db.row_factory = sqlite3.Row
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'devices' in tables:
            empty['devices'] = [dict(row) for row in db.execute(
                'SELECT ip, online FROM devices WHERE (? IS NULL OR ip=?)', (target_ip, target_ip))]
        if {'scans', 'observations'} <= tables:
            empty['history'] = [dict(row) for row in db.execute('''
                SELECT s.id, s.checked, count(o.ip) AS total,
                       coalesce(sum(o.online), 0) AS online,
                       avg(CASE WHEN o.ping_upper_bound=0 THEN o.ping_ms END) AS ping
                FROM scans s LEFT JOIN observations o ON s.id=o.scan_id
                WHERE s.checked>=? AND (? IS NULL OR o.ip=?)
                GROUP BY s.id ORDER BY s.id DESC LIMIT 400''', (cutoff, target_ip, target_ip))][::-1]
            empty['availability'] = [dict(row) for row in db.execute('''
                SELECT o.ip, count(*) AS samples, sum(o.online) AS online,
                       avg(CASE WHEN o.ping_upper_bound=0 THEN o.ping_ms END) AS ping
                FROM observations o JOIN scans s ON s.id=o.scan_id
                WHERE s.checked>=? AND (? IS NULL OR o.ip=?)
                GROUP BY o.ip ORDER BY o.ip''', (cutoff, target_ip, target_ip))]
        if 'service_checks' in tables:
            empty['services'] = [dict(row) for row in db.execute(
                'SELECT * FROM service_checks WHERE (? IS NULL OR ip=?) ORDER BY ip', (target_ip, target_ip))]
    return empty


class HistoryChart(QWidget):
    def __init__(self, caption, color, parent=None):
        super().__init__(parent)
        self.caption, self.color = caption, QColor(color)
        self.points = []
        self.setMinimumHeight(200)

    def set_points(self, points):
        self.points = points
        self.update()

    def paintEvent(self, event):
        dark = getattr(self.window().parent(), 'theme_mode', 'light') == 'dark'
        def color(light, night):
            return QColor(night if dark else light)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(color('#ffffff', '#111d2e'))
        painter.setPen(QPen(color('#dce4ee', '#34445c')))
        painter.drawRoundedRect(QRectF(1, 1, self.width()-2, self.height()-2), 10, 10)
        painter.setPen(color('#243247', '#dce6f0'))
        painter.drawText(18, 26, self.caption)
        valid = [(stamp, value) for stamp, value in self.points if value is not None]
        if not valid:
            painter.setPen(color('#62748a', '#a3b5ca'))
            painter.drawText(18, 90, 'Noch keine Messwerte im gewählten Zeitraum')
            return
        left, right, top, bottom = 54, self.width()-24, 52, self.height()-38
        maximum = max(max(value for _, value in valid) * 1.15, 1)
        first, last = self.points[0][0], self.points[-1][0]
        duration = max(last-first, 1)
        painter.setPen(QPen(color('#dce4ee', '#34445c'), 1))
        for index in range(3):
            y = bottom - (bottom-top)*index/2
            painter.setPen(QPen(color('#dce4ee', '#34445c'), 1))
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            painter.setPen(color('#62748a', '#a3b5ca'))
            painter.drawText(8, int(y)+4, f'{maximum*index/2:.1f}')
        previous = None
        painter.setPen(QPen(color(self.color.name(), '#70e5c1' if self.color.name() == '#087f68' else '#84b6ff'), 2))
        for stamp, value in self.points:
            if value is None:
                previous = None
                continue
            point = QPointF(left + (stamp-first)/duration*(right-left),
                            bottom-value/maximum*(bottom-top))
            if previous is not None:
                painter.drawLine(previous, point)
            painter.drawEllipse(point, 2.5, 2.5)
            previous = point
        painter.setPen(color('#62748a', '#a3b5ca'))
        painter.drawText(left, self.height()-12, datetime.fromtimestamp(first).strftime('%d.%m. %H:%M'))
        painter.drawText(max(left, right-110), self.height()-12,
                         datetime.fromtimestamp(last).strftime('%d.%m. %H:%M'))


def fill_table(table, rows):
    table.setRowCount(len(rows))
    for index, values in enumerate(rows):
        for column, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setToolTip(str(value))
            table.setItem(index, column, item)


def make_table(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(40)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    return table


class StatisticsDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle('Sensor-Statistik')
        self.resize(1100, 860)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        title = QLabel('Sensor-Statistik')
        title.setObjectName('title')
        layout.addWidget(title)
        controls = QHBoxLayout()
        controls.addWidget(QLabel('Verlauf'))
        self.period = QComboBox()
        for text, hours in [('Letzte Stunde', 1), ('Letzte 24 Stunden', 24), ('Letzte 7 Tage', 168), ('Letzte 30 Tage', 720)]:
            self.period.addItem(text, hours)
        self.period.setCurrentIndex(1)
        self.period.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.period)
        button = QPushButton('Aktualisieren')
        button.clicked.connect(self.refresh)
        controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self.summary = QLabel()
        self.summary.setObjectName('summary')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        charts = QHBoxLayout()
        self.online_chart = HistoryChart('Erreichbare Geräte pro Scan', '#087f68')
        self.ping_chart = HistoryChart('Durchschnittlicher Ping pro Scan (ms)', '#2563eb')
        charts.addWidget(self.online_chart)
        charts.addWidget(self.ping_chart)
        layout.addLayout(charts)
        layout.addWidget(QLabel('Erreichbarkeit je Gerät · Anteil erfolgreicher Erkennungen im Zeitraum'))
        self.availability = make_table(['IP-Adresse', 'Messungen', 'Erreichbar', 'Ø Ping (ms)'])
        layout.addWidget(self.availability)
        layout.addWidget(QLabel('Offene Dienste · letzte Abfrage je Gerät (nur nach Geräteklick)'))
        self.services = make_table(['IP-Adresse', 'Offene TCP-Dienste', 'Abgefragt am'])
        layout.addWidget(self.services)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName('muted')
        layout.addWidget(self.note)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)
        self.refresh()

    def refresh(self):
        try:
            data = load_statistics(self.path, self.period.currentData(), getattr(self.parent(), 'target_ip', None))
            devices = data['devices']
            online = sum(row['online'] for row in devices)
            ports = sum(len(json.loads(row['ports'])) for row in data['services'])
            self.summary.setText(f"{len(devices)} Geräte gesamt · {online} online · {len(devices)-online} offline"
                                 f" · {ports} zuletzt offene TCP-Ports · {len(data['services'])} Geräte auf Dienste geprüft")
            history = data['history']
            times = [datetime.fromisoformat(row['checked']).timestamp() for row in history]
            self.online_chart.set_points(list(zip(times, [row['online'] for row in history])))
            self.ping_chart.set_points(list(zip(times, [row['ping'] for row in history])))
            fill_table(self.availability, [(row['ip'], row['samples'],
                       f"{100*row['online']/row['samples']:.1f} %",
                       f"{row['ping']:.2f}" if row['ping'] is not None else '—') for row in data['availability']])
            fill_table(self.services, [(row['ip'], ', '.join(json.loads(row['ports'])) or 'keine',
                       datetime.fromisoformat(row['checked']).astimezone().strftime('%d.%m.%Y %H:%M:%S'))
                       for row in data['services']])
            self.note.setText('Verlauf ab dem ersten Scan mit dieser Version. Fehlgeschlagene Geräteerkennung zählt nicht. '
                              'Kurven zeigen maximal die letzten 400 Scans. Erreichbarkeit ist ein Messanteil, keine zeitliche Uptime. Ping ohne Antwort und „<“-Werte '
                              'gehen nicht in den Durchschnitt ein. Dienste werden hier nicht neu gescannt.')
        except (sqlite3.Error, OSError, ValueError, KeyError) as exc:
            self.note.setText('Statistik konnte nicht aktualisiert werden: ' + str(exc))

    def showEvent(self, event):
        self.timer.start(5000)
        self.refresh()
        super().showEvent(event)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)
