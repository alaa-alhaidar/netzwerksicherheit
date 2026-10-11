import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

from scanner.fritz_router import FritzHosts, load_config, save_config


DESCRIPTION = b'''<root xmlns="urn:dslforum-org:device-1-0"><device><serviceList>
<service><serviceType>urn:dslforum-org:service:Hosts:1</serviceType>
<controlURL>/upnp/control/hosts</controlURL></service></serviceList></device></root>'''
CONFIG = dict(enabled=True, host="192.168.178.1", username="monitor", password="test-only")


def response(medium):
    return io.BytesIO(f'''<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
    <s:Body><r:X_AVM-DE_GetSpecificHostEntryByIPResponse xmlns:r="urn:dslforum-org:service:Hosts:1">
    <NewInterfaceType>{medium}</NewInterfaceType><NewMACAddress>00:11:22:33:44:55</NewMACAddress>
    <NewHostName>Test Pi</NewHostName><NewActive>1</NewActive>
    </r:X_AVM-DE_GetSpecificHostEntryByIPResponse></s:Body></s:Envelope>'''.encode())


class RouterTests(unittest.TestCase):
    def client(self, answer):
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(DESCRIPTION), answer]
        with patch('scanner.fritz_router.build_opener', return_value=opener):
            return FritzHosts(CONFIG), opener

    def test_config_private_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'db.sqlite3'
            save_config(path, CONFIG)
            stored = path.parent / 'router.json'
            self.assertEqual(stored.stat().st_mode & 0o777, 0o600)
            self.assertEqual(load_config(path), CONFIG)
            self.assertEqual(list(path.parent.glob('.router-*.tmp')), [])

    def test_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            for changes in ({'host': '8.8.8.8'}, {'password': ''}, {'host': '127.0.0.1'}):
                with self.assertRaises(ValueError):
                    save_config(Path(tmp) / 'db', CONFIG | changes)

    def test_wlan_and_read_only_request(self):
        client, opener = self.client(response('802.11'))
        info = client.host_info('192.168.178.2')
        self.assertEqual(info['type'], 'WLAN')
        self.assertEqual(info['router'], CONFIG['host'])
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'http://192.168.178.1:49000/upnp/control/hosts')
        self.assertIn('GetSpecificHostEntryByIP', request.headers['Soapaction'])
        xml = ET.fromstring(request.data)
        self.assertEqual(next(element.text for element in xml.iter() if element.tag == 'NewIPAddress'), '192.168.178.2')
        self.assertNotIn(CONFIG['password'], request.data.decode())

    def test_ethernet(self):
        client, _ = self.client(response('Ethernet'))
        self.assertEqual(client.host_info('192.168.178.2')['type'], 'Ethernet')

    def test_unknown_medium(self):
        client, _ = self.client(response('HomePlug'))
        self.assertEqual(client.host_info('192.168.178.2')['type'], 'Unbekannt')

    def test_host_not_in_router(self):
        fault = b'<Fault><errorCode>714</errorCode></Fault>'
        client, _ = self.client(HTTPError('url', 500, 'fault', {}, io.BytesIO(fault)))
        self.assertEqual(client.host_info('192.168.178.2'), {})

    def test_auth_failure_propagates(self):
        client, _ = self.client(HTTPError('url', 401, 'unauthorized', {}, io.BytesIO()))
        with self.assertRaises(HTTPError):
            client.host_info('192.168.178.2')


if __name__ == '__main__':
    unittest.main()
