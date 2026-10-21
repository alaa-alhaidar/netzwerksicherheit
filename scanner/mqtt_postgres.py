#!/usr/bin/env python3
"""Receive environmental MQTT telemetry and commit it to PostgreSQL."""
import json
import os
import sqlite3
from scanner.temperature_alarm import record_temperature
from scanner.telemetry import validate_measurements


def decode_message(raw, node_id):
    if len(raw) > 16384:
        raise ValueError('Nachricht zu groß')
    payload = json.loads(raw)
    values = validate_measurements(payload)
    if payload.get('node_id') != node_id:
        raise ValueError('Unbekannter Knoten')
    boot = payload.get('boot_id')
    seq = payload.get('sequence')
    if not isinstance(boot, str) or not 1 <= len(boot) <= 128:
        raise ValueError('Ungültige boot_id')
    if type(seq) is not int or not 0 <= seq <= 9223372036854775807:
        raise ValueError('Ungültige sequence')
    if payload.get('source') not in ('fake', 'sensor', 'nano-fake', 'nano-bme688'):
        raise ValueError('Ungültige source')
    return (payload['node_id'], boot, seq, payload['source'], *values)


def store_message(connection, sensor_ip, data):
    connection.execute('''INSERT INTO sensor_measurements
        (sensor_ip,node_id,boot_id,sequence,source,temperature_c,pressure_hpa,
         humidity_pct,gas_resistance_ohm)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (node_id,boot_id,sequence) DO NOTHING''', (sensor_ip, *data))


def main():
    import paho.mqtt.client as mqtt
    import psycopg
    node = os.getenv('MQTT_NODE_ID', 'pi-05')
    topic = f'iot/v1/nodes/{node}/telemetry'
    sensor_ip = os.getenv('SENSOR_IP', '192.168.178.124')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id=os.getenv('MQTT_CLIENT_ID', 'environment-postgres'),
                         clean_session=False,
                         manual_ack=True)
    if os.getenv('MQTT_USERNAME'):
        client.username_pw_set(os.environ['MQTT_USERNAME'], os.getenv('MQTT_PASSWORD'))
    if os.getenv('MQTT_CA_FILE'):
        client.tls_set(ca_certs=os.environ['MQTT_CA_FILE'])

    def connected(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print('MQTT-Verbindung abgelehnt', flush=True)
            return
        client.subscribe(topic, qos=1)
        print('MQTT-Empfänger bereit', flush=True)

    def received(client, userdata, message):
        try:
            if message.topic != topic or message.retain:
                raise ValueError('Falsches Topic oder retained Nachricht')
            data = decode_message(message.payload, node)
        except (ValueError, UnicodeError):
            print('Ungültige Messnachricht verworfen', flush=True)
            client.ack(message.mid, message.qos)
            return
        try:
            with psycopg.connect(connect_timeout=10) as connection:
                store_message(connection, sensor_ip, data)
            record_temperature(os.getenv('MONITOR_DB', 'data/monitor.sqlite3'), sensor_ip, data)
        except (psycopg.Error, sqlite3.Error, OSError) as exc:
            # Leave the QoS 1 message unacknowledged and restart for redelivery.
            print(f'PostgreSQL-Schreiben fehlgeschlagen: {type(exc).__name__}, '
                  f'SQLSTATE={getattr(exc, "sqlstate", None) or "unbekannt"}; Neustart erforderlich', flush=True)
            raise SystemExit(1)
        client.ack(message.mid, message.qos)
        print('Messwerte in PostgreSQL gespeichert', flush=True)

    client.on_connect = connected
    client.on_message = received
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect_async(os.getenv('MQTT_HOST', '127.0.0.1'),
                         int(os.getenv('MQTT_PORT', '1883')), 60)
    client.loop_forever(retry_first_connection=True)


if __name__ == '__main__':
    main()
