#!/usr/bin/env python3
"""Geräte zuerst mit Nmap finden, danach Metadaten und Dienste abfragen."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time

NETWORK = "auto"
COMMON_PORTS = {
    22: "SSH", 53: "DNS", 80: "HTTP", 443: "HTTPS", 445: "SMB",
    554: "RTSP", 1883: "MQTT", 3389: "RDP", 5000: "HTTP/API", 8080: "HTTP-ALT",
}


def database(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS devices (
        ip TEXT PRIMARY KEY, online INTEGER NOT NULL,
        first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
        last_checked TEXT NOT NULL)""")
    columns = {row[1] for row in db.execute("PRAGMA table_info(devices)")}
    for column in ("hostname", "mac", "ping", "services", "detail_error", "connection_info"):
        if column not in columns:
            db.execute(f"ALTER TABLE devices ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    db.execute("""CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY, checked TEXT NOT NULL, networks TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS scans_checked ON scans(checked)")
    db.execute("""CREATE TABLE IF NOT EXISTS observations (
        scan_id INTEGER NOT NULL, ip TEXT NOT NULL, online INTEGER NOT NULL,
        ping_ms REAL, ping_upper_bound INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(scan_id, ip))""")
    db.execute("CREATE INDEX IF NOT EXISTS observations_ip ON observations(ip, scan_id)")
    db.execute("""CREATE TABLE IF NOT EXISTS service_checks (
        ip TEXT PRIMARY KEY, checked TEXT NOT NULL, ports TEXT NOT NULL)""")
    db.commit()
    return db


def detect_networks():
    """Aktive direkt angeschlossene IPv4-Netze auf Linux ermitteln."""
    result = subprocess.run(["ip", "-j", "-4", "addr", "show", "up"],
                            capture_output=True, text=True, check=True, timeout=10)
    networks = set()
    for interface in json.loads(result.stdout):
        name = interface.get("ifname", "")
        if "LOOPBACK" in interface.get("flags", []) or name.startswith(
                ("lo", "docker", "br-", "veth", "virbr", "tun", "tap", "wg")):
            continue
        if interface.get("operstate") != "UP":
            continue
        for address in interface.get("addr_info", []):
            if address.get("family") != "inet" or address.get("scope") != "global":
                continue
            network = ipaddress.IPv4Interface(
                f"{address['local']}/{address['prefixlen']}").network
            if network.prefixlen == 32 or network.is_loopback or network.is_link_local:
                continue
            networks.add(network)
    if not networks:
        raise ValueError("Kein aktives lokales IPv4-Netz gefunden")
    networks = list(ipaddress.collapse_addresses(networks))
    if any(network.num_addresses > 4096 for network in networks):
        raise ValueError("Erkanntes Netz ist größer als 4096 Adressen; --network für einen Teilbereich verwenden")
    return networks


def discover_devices(network=NETWORK, timeout=300):
    """Findet zuerst alle erreichbaren Geräte im Netzwerk mit Nmap."""
    if str(network) == "auto":
        devices = set()
        for detected in detect_networks():
            devices.update(discover_devices(str(detected), timeout))
        return sorted(devices, key=ipaddress.IPv4Address)
    network = ipaddress.IPv4Network(network, strict=False)
    print(f"Suche Geräte in {network} ...\n", flush=True)
    result = subprocess.run(
        ["nmap", "-sn", str(network)], capture_output=True,
        text=True, check=True, timeout=timeout,
    )
    devices = set()
    for line in result.stdout.splitlines():
        if not line.startswith("Nmap scan report for"):
            continue
        match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)", line)
        if not match:
            match = re.search(r"(\d+\.\d+\.\d+\.\d+)$", line)
        if match:
            ip = ipaddress.IPv4Address(match.group(1))
            if ip in network:
                devices.add(str(ip))
    # Do not replace live device states with an incomplete discovery result.
    if not re.search(r"^Nmap done:", result.stdout, re.MULTILINE):
        raise ValueError("Nmap-Geräteerkennung ist unvollständig")
    return sorted(devices, key=ipaddress.IPv4Address)


def get_hostname(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except OSError:
        return "unbekannt"


def get_connection_info(ip):
    """Describe the scanner's route and local interface, not the remote device's medium."""
    try:
        result = subprocess.run(["ip", "-j", "-4", "route", "get", str(ipaddress.IPv4Address(ip))],
                                capture_output=True, text=True, check=True, timeout=5)
        route = json.loads(result.stdout)[0]
        interface = route.get("dev", "")
        if not interface:
            return {}
        result = subprocess.run(["ip", "-j", "-4", "addr", "show", "dev", interface],
                                capture_output=True, text=True, check=True, timeout=5)
        link = json.loads(result.stdout)[0]
        sys_path = Path("/sys/class/net") / interface
        if (sys_path / "wireless").exists() or (sys_path / "phy80211").exists():
            kind = "WLAN"
        elif link.get("link_type") == "ether" and (sys_path / "device").exists():
            kind = "Ethernet"
        else:
            kind = "Unbekannt / virtuell"
        source = route.get("prefsrc") or route.get("src") or ""
        address = next((addr for addr in link.get("addr_info", [])
                        if addr.get("local") == source), None)
        network = str(ipaddress.IPv4Interface(
            f"{source}/{address['prefixlen']}").network) if address else ""
        return {"type": kind, "interface": interface, "local_ip": source,
                "network": network, "gateway": route.get("gateway", ""),
                "mac": link.get("address", ""), "state": link.get("operstate", ""),
                "mtu": link.get("mtu", ""),
                "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, TypeError):
        return {}


def get_mac(ip):
    """Liest die MAC-Adresse aus der lokalen Neighbor-Tabelle."""
    try:
        subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        result = subprocess.run(["ip", "neigh", "show", ip],
                                capture_output=True, text=True, check=True, timeout=5)
        match = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", result.stdout)
        if match:
            return match.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return "unbekannt"


def get_ping(ip):
    result = subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                            capture_output=True, text=True, timeout=3,
                            env={**os.environ, "LC_ALL": "C"})
    match = re.search(r"time([=<])(\d+(?:\.\d+)?)\s*ms", result.stdout)
    if match:
        return ("<" if match.group(1) == "<" else "") + match.group(2) + " ms"
    return "keine Antwort"


def scan_ports(ip, timeout=300):
    ports_string = ",".join(str(port) for port in COMMON_PORTS)
    result = subprocess.run(
        ["nmap", "-Pn", "-p", ports_string, "--open", ip],
        capture_output=True, text=True, check=True, timeout=timeout,
    )
    if not re.search(r"^Nmap done:", result.stdout, re.MULTILINE):
        raise ValueError("Nmap-Portscan ist unvollständig")
    found = []
    for line in result.stdout.splitlines():
        match = re.match(r"(\d+)/tcp\s+open\s+(\S+)", line)
        if match:
            port = int(match.group(1))
            found.append(f"{port}/{COMMON_PORTS.get(port, match.group(2))}")
    return found


def get_device_info(ip, timeout=300):
    errors = []
    hostname = get_hostname(ip)
    mac = get_mac(ip)
    try:
        ping = get_ping(ip)
    except (OSError, subprocess.SubprocessError) as exc:
        ping = "unbekannt"
        errors.append(f"Ping: {exc}")
    services = "erst beim Öffnen der Gerätedetails abgefragt"
    print("=" * 65)
    for label, value in [("IP-Adresse", ip), ("Hostname", hostname), ("MAC", mac),
                         ("Ping", ping), ("Status", "ONLINE"), ("Dienste", services),
                         ("Scan-Zeit", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))]:
        print(f"{label:11}: {value}", flush=True)
    return {"ip": ip, "hostname": hostname, "mac": mac, "ping": ping,
            "services": services, "detail_error": "; ".join(errors)}


def scan(db, network=NETWORK, timeout=300):
    networks = detect_networks() if str(network) == "auto" else [ipaddress.IPv4Network(network, strict=False)]
    print("Erkannte Netze: " + ", ".join(map(str, networks)), flush=True)
    devices = set()
    for detected in networks:
        devices.update(discover_devices(str(detected), timeout))
    devices = sorted(devices, key=ipaddress.IPv4Address)
    print(f"{len(devices)} Geräte gefunden.\n", flush=True)
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Persist discovery before collecting details, so Qt can show all hosts first.
    with db:
        scan_id = db.execute("INSERT INTO scans (checked, networks) VALUES (?, ?)",
                             (checked, ", ".join(map(str, networks)))).lastrowid
        for (ip,) in db.execute("SELECT ip FROM devices").fetchall():
            if str(network) == "auto" or any(ipaddress.IPv4Address(ip) in detected for detected in networks):
                db.execute("UPDATE devices SET online=0, last_checked=? WHERE ip=?", (checked, ip))
        for ip in devices:
            db.execute("""INSERT INTO devices (ip, online, first_seen, last_seen, last_checked)
                VALUES (?, 1, ?, ?, ?) ON CONFLICT(ip) DO UPDATE SET
                online=1, last_seen=excluded.last_seen, last_checked=excluded.last_checked""",
                (ip, checked, checked, checked))
            db.execute("""UPDATE devices SET hostname='', mac='', ping='',
                detail_error='' WHERE ip=?""", (ip,))
        for ip, online in db.execute("SELECT ip, online FROM devices").fetchall():
            # Only the discovered subnets count as measured, especially after a network change.
            if any(ipaddress.IPv4Address(ip) in detected for detected in networks):
                db.execute("INSERT INTO observations (scan_id, ip, online) VALUES (?, ?, ?)",
                           (scan_id, ip, online))
    for ip in devices:
        info = get_device_info(ip, timeout)
        with db:
            db.execute("""UPDATE devices SET hostname=:hostname, mac=:mac,
                ping=:ping, detail_error=:detail_error WHERE ip=:ip""", info)
            match = re.fullmatch(r"(<)?(\d+(?:\.\d+)?) ms", info["ping"])
            if match:
                db.execute("""UPDATE observations SET ping_ms=?, ping_upper_bound=?
                    WHERE scan_id=? AND ip=?""",
                    (float(match.group(2)), int(bool(match.group(1))), scan_id, ip))
        # Notify the GUI after the result is committed, rather than waiting for the next host.
        print(f"Gerätestatus aktualisiert: {ip}", flush=True)
        connection = get_connection_info(ip)
        with db:
            db.execute("UPDATE devices SET connection_info=? WHERE ip=?",
                       (json.dumps(connection), ip))
    print(f"\n{'=' * 65}\nScan abgeschlossen: {len(devices)} Geräte gefunden.", flush=True)


def scan_target(db, ip, timeout=30):
    """Monitor one configured sensor address without scanning surrounding devices."""
    ip = str(ipaddress.IPv4Address(ip))
    online = ip in discover_devices(f"{ip}/32", timeout)
    checked = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with db:
        scan_id = db.execute("INSERT INTO scans(checked,networks) VALUES(?,?)",
                             (checked, f"{ip}/32")).lastrowid
        db.execute("""INSERT INTO devices(ip,online,first_seen,last_seen,last_checked,ping)
            VALUES(?,?,?,?,?,?) ON CONFLICT(ip) DO UPDATE SET
            online=excluded.online,last_checked=excluded.last_checked,ping=excluded.ping,
            last_seen=CASE WHEN excluded.online=1 THEN excluded.last_seen ELSE devices.last_seen END""",
            (ip, int(online), checked, checked if online else "1970-01-01T00:00:00+00:00", checked,
             "" if online else "keine Antwort"))
        db.execute("INSERT INTO observations(scan_id,ip,online) VALUES(?,?,?)",
                   (scan_id, ip, int(online)))
    print(f"Sensorstatus aktualisiert: {ip}", flush=True)
    if online:
        info = get_device_info(ip, timeout)
        with db:
            db.execute("""UPDATE devices SET hostname=:hostname,mac=:mac,ping=:ping,
                detail_error=:detail_error WHERE ip=:ip""", info)
            match = re.fullmatch(r"(<)?(\d+(?:\.\d+)?) ms", info["ping"])
            if match:
                db.execute("UPDATE observations SET ping_ms=?,ping_upper_bound=? WHERE scan_id=? AND ip=?",
                           (float(match.group(2)), int(bool(match.group(1))), scan_id, ip))
        print(f"Sensorantwort aktualisiert: {ip}", flush=True)
    with db:
        db.execute("UPDATE devices SET connection_info=? WHERE ip=?",
                   (json.dumps(get_connection_info(ip)), ip))
    print(f"Scan abgeschlossen: Sensor {ip} geprüft.", flush=True)


def main():
    def stop_requested(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_requested)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", default=os.getenv("NETWORK_CIDR", NETWORK))
    default_db = Path(__file__).resolve().parents[1] / "data" / "monitor.sqlite3"
    parser.add_argument("--db", default=os.getenv("MONITOR_DB", str(default_db)))
    parser.add_argument("--interval", type=int, default=int(os.getenv("SCAN_INTERVAL", "60")))
    parser.add_argument("--timeout", type=int, default=300, help="Zeitlimit pro Nmap-Aufruf in Sekunden")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--ports-ip", help="Nur Dienste eines Geräts abfragen")
    parser.add_argument("--target-ip", help="Nur diesen Sensor überwachen, keine Netzwerksuche")
    args = parser.parse_args()
    if args.ports_ip:
        try:
            ip = str(ipaddress.IPv4Address(args.ports_ip))
            if args.timeout < 1:
                raise ValueError("Zeitlimit muss positiv sein")
            ports = scan_ports(ip, args.timeout)
            with database(args.db) as db:
                db.execute("INSERT OR REPLACE INTO service_checks VALUES (?, ?, ?)",
                           (ip, datetime.now(timezone.utc).isoformat(timespec="seconds"), json.dumps(ports)))
            print(json.dumps({"services": ", ".join(ports) if ports else "keine getesteten Ports offen"}))
            return 0
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(str(exc), file=sys.stderr)
            return 1
    network = args.network
    if args.target_ip:
        try:
            args.target_ip = str(ipaddress.IPv4Address(args.target_ip))
        except ValueError as exc:
            parser.error(str(exc))
    if network != "auto":
        try:
            network = ipaddress.IPv4Network(network, strict=False)
        except ValueError as exc:
            parser.error(str(exc))
        if network.num_addresses > 4096:
            parser.error("Maximal 4096 Adressen pro Scan sind erlaubt")
    if args.interval < 1 or args.timeout < 1:
        parser.error("Intervall und Zeitlimit müssen positiv sein")
    for executable in ("nmap", "ping", "ip"):
        if not shutil.which(executable):
            parser.error(f"{executable} fehlt: installiere nmap, iputils-ping und iproute2")
    print("\nRaspberry Pi Network Monitor\n============================\n", flush=True)
    db = database(args.db)
    try:
        while True:
            try:
                if args.target_ip:
                    scan_target(db, args.target_ip, args.timeout)
                else:
                    scan(db, network, args.timeout)
            except (subprocess.SubprocessError, OSError, ValueError) as exc:
                print(f"Geräteerkennung fehlgeschlagen: {exc}", file=sys.stderr, flush=True)
                if args.once:
                    return 1
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
