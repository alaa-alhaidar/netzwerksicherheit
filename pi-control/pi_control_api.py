"""Local, token-protected control API for Sensor Campus services on Pi 5."""

import hmac
import json
import math
import os
import socket
import subprocess
import sys
import time
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paho.mqtt.client as mqtt


HOST = os.getenv("PI_CONTROL_HOST", "127.0.0.1")
PORT = int(os.getenv("PI_CONTROL_PORT", "8765"))
TOKEN = os.environ["PI_CONTROL_TOKEN"]
MQTT_SERVICE = "pi-mqtt.service"
SERVICES = ("pi-alarm.service", "pi-telemetry.service")
COMPOSE_FILE = "/home/alaa/network-monitor~/docker/compose-cloud.yaml"
DOCKER_SERVICES = {"postgres", "sync", "pdc"}
TELEMETRY_TOPIC = "iot/v1/nodes/pi-05/telemetry"
ALARM_TOPIC = "iot/v1/nodes/pi-05/commands/alarm"
ALARM_STATE_TOPIC = "iot/v1/nodes/pi-05/state/alarm"
TOLERANCE_FILE = "/home/alaa/pi-control/tolerance.json"
RANGE_BOUNDS = {
    "temperature_c": (-100.0, 200.0),
    "pressure_hpa": (100.0, 1500.0),
    "humidity_pct": (0.0, 100.0),
    "gas_resistance_ohm": (0.0, 1_000_000_000.0),
}


def validate_ranges(value):
    if not isinstance(value, dict) or set(value) != set(RANGE_BOUNDS):
        raise ValueError("Für alle vier Messgrößen sind Bereiche erforderlich")
    cleaned = {}
    for key, bounds in RANGE_BOUNDS.items():
        limits = value.get(key)
        if not isinstance(limits, dict):
            raise ValueError(f"Ungültiger Bereich für {key}")
        minimum, maximum = limits.get("min"), limits.get("max")
        if (not isinstance(minimum, (int, float)) or isinstance(minimum, bool)
                or not isinstance(maximum, (int, float)) or isinstance(maximum, bool)
                or not math.isfinite(minimum) or not math.isfinite(maximum)):
            raise ValueError(f"Min und Max für {key} müssen Zahlen sein")
        if minimum >= maximum:
            raise ValueError(f"Minimum für {key} muss kleiner als Maximum sein")
        if minimum < bounds[0] or maximum > bounds[1]:
            raise ValueError(
                f"{key} muss zwischen {bounds[0]:g} und {bounds[1]:g} liegen"
            )
        cleaned[key] = {"min": float(minimum), "max": float(maximum)}
    return cleaned


def read_tolerance_state():
    try:
        with open(TOLERANCE_FILE, encoding="utf-8") as state_file:
            state = json.load(state_file)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def save_ranges(value):
    ranges = validate_ranges(value)
    state = read_tolerance_state()
    state["ranges"] = ranges
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path = Path(TOLERANCE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".api.tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(path)
    return ranges


def service_state(service):
    result = subprocess.run(
        ["systemctl", "--user", "is-active", service],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def mqtt_available():
    try:
        with socket.create_connection(("127.0.0.1", 1883), timeout=2):
            return True
    except OSError:
        return False


def docker_services_running():
    result = subprocess.run(
        ["docker", "compose", "-f", COMPOSE_FILE, "--profile", "pdc",
         "ps", "--status", "running", "--services"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return DOCKER_SERVICES.issubset(set(result.stdout.splitlines()))


def monitor_action(action):
    root = Path(COMPOSE_FILE).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/control-services.py"), action,
         "--db", str(root / "data/monitor.sqlite3")],
        capture_output=True, text=True, timeout=660 if action != "status" else 60,
    )
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError("Dienstesteuerung lieferte keine gültige Antwort")
    if result.returncode or "error" in payload:
        raise RuntimeError(payload.get("error", "Dienstesteuerung fehlgeschlagen"))
    return payload


def current_status():
    try:
        state = monitor_action("status")
        services = state["services"]
        mqtt_state = "active" if services.get("mqtt") == "running" else "unavailable"
        docker = all(services.get(name) == "running" for name in ("scanner", "postgres", "sync", "pdc"))
        return {
            "running": all(value == "running" for value in services.values()) and state["hardware"] == "active",
            "mqtt": mqtt_state,
            "docker": "active" if docker else "incomplete",
            "scanner": services.get("scanner", "stopped"),
            "services": {
                "pi-alarm.service": state["hardware"],
                "pi-telemetry.service": "active" if services.get("telemetry") == "running" else services.get("telemetry", "inactive"),
                "pi-mqtt.service": mqtt_state,
            },
        }
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        return {"running": False, "mqtt": "unknown", "docker": "unknown",
                "scanner": "unknown", "services": {}, "error": str(error)}


def receive_telemetry():
    received = threading.Event()
    result = {}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(connected, userdata, flags, reason_code, properties):
        connected.subscribe(TELEMETRY_TOPIC, qos=1)

    def on_message(connected, userdata, message):
        try:
            result["payload"] = json.loads(message.payload.decode("utf-8"))
            received.set()
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("127.0.0.1", 1883, 10)
    client.loop_start()
    try:
        if not received.wait(7):
            raise TimeoutError("Keine MQTT-Sensordaten")
        payload = result["payload"]
        try:
            with open(TOLERANCE_FILE, encoding="utf-8") as tolerance_file:
                payload["alarm_control"] = json.load(tolerance_file)
        except (OSError, ValueError, TypeError):
            pass
        return payload
    finally:
        client.disconnect()
        client.loop_stop()


def publish_alarm(enabled):
    request_id = str(uuid.uuid4())
    confirmed = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(connected, userdata, flags, reason_code, properties):
        connected.subscribe(ALARM_STATE_TOPIC, qos=1)
        connected.publish(ALARM_TOPIC, json.dumps({
            "enabled": enabled,
            "request_id": request_id,
        }), qos=1, retain=False)

    def on_message(connected, userdata, message):
        try:
            state = json.loads(message.payload.decode("utf-8"))
            if state.get("request_id") == request_id and state.get("enabled") is enabled:
                confirmed.set()
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("127.0.0.1", 1883, 10)
    client.loop_start()
    try:
        if not confirmed.wait(7):
            raise TimeoutError("Alarmbefehl wurde nicht bestätigt")
    finally:
        client.disconnect()
        client.loop_stop()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def authorized(self):
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {TOKEN}")

    def reject_unauthorized(self):
        self.send_json(401, {"error": "Nicht autorisiert"})

    def do_GET(self):
        if not self.authorized():
            return self.reject_unauthorized()
        if self.path == "/status":
            return self.send_json(200, current_status())
        if self.path == "/telemetry":
            try:
                return self.send_json(200, receive_telemetry())
            except (OSError, TimeoutError) as error:
                return self.send_json(503, {"error": str(error)})
        if self.path == "/ranges":
            ranges = read_tolerance_state().get("ranges")
            try:
                return self.send_json(200, {"ranges": validate_ranges(ranges)})
            except ValueError:
                return self.send_json(404, {"error": "Noch keine Bereiche konfiguriert"})
        return self.send_json(404, {"error": "Nicht gefunden"})

    def do_POST(self):
        if not self.authorized():
            return self.reject_unauthorized()
        if self.path == "/ranges":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                ranges = save_ranges(body.get("ranges"))
                return self.send_json(200, {"ok": True, "ranges": ranges})
            except (AttributeError, ValueError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            except OSError as error:
                return self.send_json(500, {"error": f"Bereiche konnten nicht gespeichert werden: {error}"})

        if self.path == "/alarm":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length))
                enabled = body["enabled"]
                if not isinstance(enabled, bool):
                    raise ValueError("enabled muss ein Boolean sein")
                publish_alarm(enabled)
                return self.send_json(200, {"ok": True, "enabled": enabled})
            except (KeyError, ValueError, json.JSONDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            except (OSError, TimeoutError) as error:
                return self.send_json(503, {"error": str(error)})

        actions = {"/start": "start", "/stop": "stop"}
        action = actions.get(self.path)
        if action is None:
            return self.send_json(404, {"error": "Nicht gefunden"})
        try:
            monitor_action(action)
        except (subprocess.SubprocessError, OSError, RuntimeError, ValueError) as error:
            return self.send_json(500, {"error": f"Dienstaktion fehlgeschlagen: {error}"})
        status = current_status()
        if action == "start":
            for _ in range(10):
                if status["running"]:
                    break
                time.sleep(0.5)
                status = current_status()
        if action == "start" and status["mqtt"] != "active":
            return self.send_json(503, {**status, "error": "MQTT-Broker ist nicht erreichbar"})
        if action == "start" and not status["running"]:
            return self.send_json(503, {**status, "error": "Dienste noch nicht vollständig gestartet"})
        self.send_json(200, status)

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} {fmt % args}", flush=True)


if __name__ == "__main__":
    print(f"Pi control API auf http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
