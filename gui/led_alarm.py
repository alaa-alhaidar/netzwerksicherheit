"""Optional Pi 5 GPIO LED alarm; all GPIO access stays outside scanner processes."""
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


def make_led(pin):
    from gpiozero import LED
    from gpiozero.pins.lgpio import LGPIOFactory
    factory = LGPIOFactory()
    try:
        return LED(pin, initial_value=False, pin_factory=factory), factory
    except Exception:
        factory.close()
        raise


class LEDAlarm(QObject):
    statusChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.led = None
        self.factory = None
        self.active = False
        self.status = "LED-Alarm deaktiviert"
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.toggle)

    def report(self, status):
        self.status = status
        self.statusChanged.emit(status)

    def configure(self, enabled, pin=17):
        self.close()
        if not enabled:
            self.report("LED-Alarm deaktiviert")
            return
        try:
            if not 2 <= pin <= 27:
                raise ValueError("GPIO-Nummer muss zwischen 2 und 27 liegen")
            self.led, self.factory = make_led(pin)
            self.report(f"LED an GPIO{pin} bereit")
            self.update_output()
        except Exception:
            self.close()
            self.report("LED nicht verfügbar: GPIO-Zugriff und gpiozero/lgpio prüfen.")

    def set_active(self, active):
        active = bool(active)
        if self.active != active:
            self.active = active
            self.update_output()

    def update_output(self):
        if self.led is None:
            return
        try:
            if self.active:
                self.led.on()
                self.timer.start()
            else:
                self.timer.stop()
                self.led.off()
        except Exception:
            self.fail()

    def toggle(self):
        try:
            if self.led is not None:
                self.led.toggle()
        except Exception:
            self.fail()

    def fail(self):
        self.close()
        self.report("LED-Ansteuerung fehlgeschlagen; Bildschirmalarme bleiben aktiv.")

    def close(self):
        self.timer.stop()
        for device in (self.led, self.factory):
            if device is not None:
                try:
                    if device is self.led:
                        device.off()
                except Exception:
                    pass
                try:
                    device.close()
                except Exception:
                    pass
        self.led = self.factory = None
