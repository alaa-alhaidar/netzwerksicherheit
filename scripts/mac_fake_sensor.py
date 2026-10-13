#!/usr/bin/env python3
"""Send clearly marked simulated environmental readings over MQTT."""
import argparse
from datetime import datetime, timezone
import json
import math
import os
import time
import uuid


def main():
    import paho.mqtt.client as mqtt
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=1883)
    parser.add_argument('--node-id', default='lab-01')
    parser.add_argument('--interval', type=float, default=5)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval <= 0:
        parser.error('Intervall muss positiv und endlich sein')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if os.getenv('MQTT_USERNAME'):
        client.username_pw_set(os.environ['MQTT_USERNAME'], os.getenv('MQTT_PASSWORD'))
    if os.getenv('MQTT_CA_FILE'):
        client.tls_set(ca_certs=os.environ['MQTT_CA_FILE'])
    client.connect(args.host, args.port, 60)
    client.loop_start()
    boot, sequence = str(uuid.uuid4()), 0
    try:
        while True:
            phase = sequence / 12
            payload = {'schema_version': 1, 'node_id': args.node_id,
                'boot_id': boot, 'sequence': sequence,
                'sent_at': datetime.now(timezone.utc).isoformat(), 'source': 'fake',
                'measurements': {
                    'temperature_c': round(23 + 2 * math.sin(phase), 2),
                    'pressure_hpa': round(1013 + 3 * math.sin(phase / 3), 2),
                    'humidity_pct': round(48 + 5 * math.cos(phase), 2),
                    'gas_resistance_ohm': round(120000 + 10000 * math.sin(phase / 2))}}
            info = client.publish(f'iot/v1/nodes/{args.node_id}/telemetry',
                                  json.dumps(payload), qos=1, retain=False)
            info.wait_for_publish(timeout=15)
            if not info.is_published():
                raise RuntimeError('MQTT-Senden nicht bestätigt')
            print('SIMULIERT:', json.dumps(payload['measurements']), flush=True)
            sequence += 1
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
