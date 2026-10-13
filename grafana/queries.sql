-- Dashboard queries: only 192.168.178.124.

-- Geräte gesamt
SELECT count(*) AS "Geräte gesamt" FROM devices WHERE ip='192.168.178.124';

-- Online
SELECT count(*) AS "Online" FROM devices WHERE ip='192.168.178.124' AND online=1;

-- Offline
SELECT count(*) AS "Offline" FROM devices WHERE ip='192.168.178.124' AND online=0;

-- Temperatur
SELECT temperature_c AS "Temperatur" FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at DESC,id DESC LIMIT 1;

-- Luftdruck
SELECT pressure_hpa AS "Luftdruck" FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at DESC,id DESC LIMIT 1;

-- Luftfeuchtigkeit
SELECT humidity_pct AS "Luftfeuchtigkeit" FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at DESC,id DESC LIMIT 1;

-- Gas · Widerstand
SELECT gas_resistance_ohm AS "Gas · Widerstand" FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at DESC,id DESC LIMIT 1;

-- Temperatur – Verlauf
SELECT received_at AS "time", temperature_c AS "Temperatur"
FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at,id;

-- Luftdruck – Verlauf
SELECT received_at AS "time", pressure_hpa AS "Luftdruck"
FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at,id;

-- Luftfeuchtigkeit – Verlauf
SELECT received_at AS "time", humidity_pct AS "Luftfeuchtigkeit"
FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at,id;

-- Gas · Widerstand – Verlauf
SELECT received_at AS "time", gas_resistance_ohm AS "Gas · Widerstand"
FROM sensor_measurements
WHERE sensor_ip='192.168.178.124' AND $__timeFilter(received_at)
ORDER BY received_at,id;

-- Erreichbare Geräte im Verlauf
SELECT s.checked AS "time", coalesce(sum(o.online),0) AS "Erreichbare Geräte"
FROM scans s JOIN observations o ON o.scan_id=s.id
WHERE o.ip='192.168.178.124' AND $__timeFilter(s.checked)
GROUP BY s.id,s.checked ORDER BY s.checked,s.id;

-- Latenz – 192.168.178.124
SELECT s.checked AS "time", o.ip AS metric, o.ping_ms AS value
FROM observations o JOIN scans s ON s.id=o.scan_id
WHERE o.ip='192.168.178.124' AND $__timeFilter(s.checked)
AND o.ping_ms IS NOT NULL AND o.ping_upper_bound=0
ORDER BY s.checked,s.id,o.ip;
