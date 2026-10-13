"""Validate the four environmental measurements shared by Mac and sensor senders."""
import math

FIELDS = ("temperature_c", "pressure_hpa", "humidity_pct", "gas_resistance_ohm")


def validate_measurements(payload):
    """Return ordered finite numeric measurements; reject incomplete messages."""
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("schema_version muss 1 sein")
    measurements = payload.get("measurements")
    if not isinstance(measurements, dict):
        raise ValueError("measurements fehlt")
    values = []
    for field in FIELDS:
        value = measurements.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{field} muss eine Zahl sein")
        try:
            value = float(value)
        except (ValueError, OverflowError):
            raise ValueError(f"{field} muss endlich sein") from None
        if not math.isfinite(value):
            raise ValueError(f"{field} muss endlich sein")
        values.append(value)
    temperature, pressure, humidity, gas = values
    if temperature < -273.15 or pressure <= 0 or not 0 <= humidity <= 100 or gas < 0:
        raise ValueError("Messwert außerhalb des erlaubten Bereichs")
    return tuple(values)
