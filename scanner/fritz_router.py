"""Read-only FRITZ!Box host lookup using TR-064 and HTTP Digest authentication."""
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from urllib.error import HTTPError
from urllib.request import HTTPDigestAuthHandler, HTTPPasswordMgrWithDefaultRealm, ProxyHandler, Request, build_opener
import xml.etree.ElementTree as ET


def config_path(db_path):
    return Path(db_path).resolve().parent / "router.json"


def load_config(db_path):
    try:
        config = json.loads(config_path(db_path).read_text())
        return config if isinstance(config, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(db_path, config):
    address = ipaddress.IPv4Address(config["host"])
    if not address.is_private or address.is_loopback or address.is_unspecified or address.is_multicast:
        raise ValueError("Bitte die lokale IPv4-Adresse der FRITZ!Box eingeben.")
    if config.get("enabled") and not (config.get("username") and config.get("password")):
        raise ValueError("Für die Abfrage sind Benutzername und Passwort erforderlich.")
    path = config_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".router-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def values(root):
    return {element.tag.split("}")[-1]: element.text or "" for element in root.iter()}


class FritzHosts:
    def __init__(self, config):
        address = ipaddress.IPv4Address(config["host"])
        self.host = str(address)
        self.base = f"http://{address}:49000"
        passwords = HTTPPasswordMgrWithDefaultRealm()
        passwords.add_password(None, self.base, config["username"], config["password"])
        self.opener = build_opener(ProxyHandler({}), HTTPDigestAuthHandler(passwords))
        with self.opener.open(self.base + "/tr64desc.xml", timeout=3) as response:
            description = ET.fromstring(response.read(2_000_000))
        self.service = None
        for element in description.iter():
            if element.tag.split("}")[-1] != "service":
                continue
            data = values(element)
            service = data.get("serviceType", "")
            if service.startswith("urn:dslforum-org:service:Hosts:"):
                control = data.get("controlURL", "")
                if not control.startswith("/") or control.startswith("//"):
                    raise ValueError("Invalid Hosts control URL")
                self.service, self.control = service, self.base + control
                break
        if self.service is None:
            raise ValueError("Hosts service unavailable")

    def host_info(self, ip):
        action = "X_AVM-DE_GetSpecificHostEntryByIP"
        envelope = ET.Element("{http://schemas.xmlsoap.org/soap/envelope/}Envelope")
        envelope.set("{http://schemas.xmlsoap.org/soap/envelope/}encodingStyle",
                     "http://schemas.xmlsoap.org/soap/encoding/")
        body = ET.SubElement(envelope, "{http://schemas.xmlsoap.org/soap/envelope/}Body")
        call = ET.SubElement(body, f"{{{self.service}}}{action}")
        ET.SubElement(call, "NewIPAddress").text = str(ipaddress.IPv4Address(ip))
        request = Request(self.control, data=ET.tostring(envelope, encoding="utf-8", xml_declaration=True),
                          headers={"Content-Type": 'text/xml; charset="utf-8"',
                                   "SOAPAction": f'"{self.service}#{action}"'})
        try:
            with self.opener.open(request, timeout=3) as response:
                result = values(ET.fromstring(response.read(200_000)))
        except HTTPError as exc:
            if exc.code == 500:
                result = values(ET.fromstring(exc.read(200_000)))
                if result.get("errorCode") == "714":
                    return {}
            raise
        if "errorCode" in result:
            if result["errorCode"] == "714":
                return {}
            raise ValueError("Router lookup failed")
        medium = result.get("NewInterfaceType", "")
        kind = {"802.11": "WLAN", "Ethernet": "Ethernet"}.get(medium, "Unbekannt")
        return {"type": kind, "interface_type": medium, "router": self.host,
                "hostname": result.get("NewHostName", ""),
                "mac": result.get("NewMACAddress", ""),
                "active": result.get("NewActive", ""),
                "port": result.get("NewX_AVM-DE_Port", ""),
                "speed": result.get("NewX_AVM-DE_Speed", ""),
                "checked": datetime.now(timezone.utc).isoformat(timespec="seconds")}
