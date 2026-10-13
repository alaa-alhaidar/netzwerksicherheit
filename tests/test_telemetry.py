import unittest
from scanner.telemetry import validate_measurements


class TelemetryTests(unittest.TestCase):
    def payload(self):
        return {"schema_version": 1, "measurements": {
            "temperature_c": 23.4, "pressure_hpa": 1012.3,
            "humidity_pct": 48.1, "gas_resistance_ohm": 120000}}

    def test_valid_measurements_use_database_column_order(self):
        self.assertEqual(validate_measurements(self.payload()), (23.4, 1012.3, 48.1, 120000))

    def test_missing_or_invalid_measurements_are_rejected(self):
        for field, value in (("temperature_c", None), ("temperature_c", True),
                             ("pressure_hpa", 0), ("humidity_pct", 101),
                             ("gas_resistance_ohm", -1), ("temperature_c", float("nan")),
                             ("pressure_hpa", float("inf"))):
            with self.subTest(field=field, value=value):
                payload = self.payload()
                payload["measurements"][field] = value
                with self.assertRaises(ValueError):
                    validate_measurements(payload)

    def test_wrong_schema_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_measurements({"schema_version": 2})

class MqttTelemetryTests(unittest.TestCase):
    def payload(self):
        return {**TelemetryTests().payload(), 'node_id': 'lab-01',
                'boot_id': 'test-boot', 'sequence': 1, 'source': 'fake'}

    def test_message_identity_and_values(self):
        import json
        from scanner.mqtt_postgres import decode_message
        self.assertEqual(decode_message(json.dumps(self.payload()), 'lab-01'),
                         ('lab-01', 'test-boot', 1, 'fake', 23.4, 1012.3, 48.1, 120000))

    def test_wrong_node_and_invalid_identity_are_rejected(self):
        import json
        from scanner.mqtt_postgres import decode_message
        for field, value in [('node_id', 'other'), ('boot_id', ''),
                             ('sequence', True), ('sequence', -1), ('source', 'unknown')]:
            with self.subTest(field=field):
                payload = self.payload()
                payload[field] = value
                with self.assertRaises(ValueError):
                    decode_message(json.dumps(payload), 'lab-01')

    def test_database_insert_uses_parameters_and_deduplication(self):
        from unittest.mock import Mock
        from scanner.mqtt_postgres import store_message
        db = Mock()
        data = ('lab-01', 'boot', 1, 'fake', 23, 1013, 48, 120000)
        store_message(db, '192.168.178.124', data)
        sql, values = db.execute.call_args.args
        self.assertIn('ON CONFLICT (node_id,boot_id,sequence) DO NOTHING', sql)
        self.assertEqual(values, ('192.168.178.124', *data))
