-- Panel: Geräte gesamt / online / offline (Format Table, Stat visualization)
SELECT count(*) AS gesamt,
       count(*) FILTER (WHERE online=1) AS online,
       count(*) FILTER (WHERE online=0) AS offline
FROM devices;

-- Panel: Erreichbare Geräte pro Scan (Format Time series)
SELECT s.checked AS "time", coalesce(sum(o.online),0) AS "Erreichbare Geräte"
FROM scans s LEFT JOIN observations o ON o.scan_id=s.id
WHERE $__timeFilter(s.checked)
GROUP BY s.id,s.checked ORDER BY s.checked;

-- Panel: Pingverlauf je Gerät (Format Time series)
SELECT s.checked AS "time", o.ip AS metric, o.ping_ms AS value
FROM observations o JOIN scans s ON s.id=o.scan_id
WHERE $__timeFilter(s.checked) AND o.ping_ms IS NOT NULL AND o.ping_upper_bound=0
ORDER BY s.checked;

-- Panel: Erreichbarkeitsquote (Format Table)
SELECT o.ip, count(*) AS messungen,
       round(100.0*sum(o.online)/count(*),1) AS erreichbar_prozent
FROM observations o JOIN scans s ON s.id=o.scan_id
WHERE $__timeFilter(s.checked)
GROUP BY o.ip ORDER BY o.ip;

-- Panel: Letzte Dienste-Abfrage (Format Table)
SELECT ip, checked AS abgefragt_am, ports FROM service_checks ORDER BY ip;
