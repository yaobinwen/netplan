#!/usr/bin/python3
# Blackbox tests of NetworkManager netplan backend. These are run during
# "make check" and don't touch the system configuration at all.
#
# Copyright (C) 2020 Canonical, Ltd.
# Author: Lukas Märdian <lukas.maerdian@canonical.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import shutil
import ctypes
import ctypes.util

from generator.base import TestBase
from tests.test_utils import MockCmd

rootdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
exe_cli = os.path.join(rootdir, 'src', 'netplan.script')
# Make sure we can import our development netplan.
os.environ.update({'PYTHONPATH': '.'})

lib = ctypes.CDLL(ctypes.util.find_library('netplan'))
lib.netplan_get_id_from_nm_filename.restype = ctypes.c_char_p


class TestNetworkManagerBackend(TestBase):
    '''Test libnetplan functionality as used by NetworkManager backend'''

    def setUp(self):
        super().setUp()
        os.makedirs(self.confdir)

    def tearDown(self):
        shutil.rmtree(self.workdir.name)
        super().tearDown()

    def test_get_id_from_filename(self):
        out = lib.netplan_get_id_from_nm_filename(
          '/run/NetworkManager/system-connections/netplan-some-id.nmconnection'.encode(), None)
        self.assertEqual(out, b'some-id')

    def test_get_id_from_filename_wifi(self):
        out = lib.netplan_get_id_from_nm_filename(
          '/run/NetworkManager/system-connections/netplan-some-id-SOME-SSID.nmconnection'.encode(), 'SOME-SSID'.encode())
        self.assertEqual(out, b'some-id')

    def test_get_id_from_filename_wifi_invalid_suffix(self):
        out = lib.netplan_get_id_from_nm_filename(
          '/run/NetworkManager/system-connections/netplan-some-id-SOME-SSID'.encode(), 'SOME-SSID'.encode())
        self.assertEqual(out, None)

    def test_get_id_from_filename_invalid_prefix(self):
        out = lib.netplan_get_id_from_nm_filename('INVALID/netplan-some-id.nmconnection'.encode(), None)
        self.assertEqual(out, None)

    def test_generate(self):
        self.mock_netplan_cmd = MockCmd("netplan")
        os.environ["TEST_NETPLAN_CMD"] = self.mock_netplan_cmd.path
        self.assertTrue(lib.netplan_generate(self.workdir.name.encode()))
        self.assertEquals(self.mock_netplan_cmd.calls(), [
            ["netplan", "generate", "--root-dir", self.workdir.name],
        ])

    def test_delete_connection(self):
        os.environ["TEST_NETPLAN_CMD"] = exe_cli
        FILENAME = os.path.join(self.confdir, 'some-filename.yaml')
        with open(FILENAME, 'w') as f:
            f.write('''network:
  ethernets:
    some-netplan-id:
      dhcp4: true''')
        self.assertTrue(os.path.isfile(FILENAME))
        # Parse all YAML and delete 'some-netplan-id' connection file
        self.assertTrue(lib.netplan_delete_connection('some-netplan-id'.encode(), self.workdir.name.encode()))
        self.assertFalse(os.path.isfile(FILENAME))

    def test_delete_connection_id_not_found(self):
        FILENAME = os.path.join(self.confdir, 'some-filename.yaml')
        with open(FILENAME, 'w') as f:
            f.write('''network:
  ethernets:
    some-netplan-id:
      dhcp4: true''')
        self.assertTrue(os.path.isfile(FILENAME))
        self.assertFalse(lib.netplan_delete_connection('unknown-id'.encode(), self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(FILENAME))

    def test_delete_connection_two_in_file(self):
        os.environ["TEST_NETPLAN_CMD"] = exe_cli
        FILENAME = os.path.join(self.confdir, 'some-filename.yaml')
        with open(FILENAME, 'w') as f:
            f.write('''network:
  ethernets:
    some-netplan-id:
      dhcp4: true
    other-id:
      dhcp6: true''')
        self.assertTrue(os.path.isfile(FILENAME))
        self.assertTrue(lib.netplan_delete_connection('some-netplan-id'.encode(), self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(FILENAME))
        # Verify the file still exists and still contains the other connection
        with open(FILENAME, 'r') as f:
            self.assertEquals(f.read(), 'network:\n  ethernets:\n    other-id:\n      dhcp6: true\n')

    def test_serialize_gsm(self):
        self.maxDiff = None
        UUID = 'a08c5805-7cf5-43f7-afb9-12cb30f6eca3'
        file = '''[connection]
id=T-Mobile Funkadelic 2
uuid=a08c5805-7cf5-43f7-afb9-12cb30f6eca3
type=gsm

[gsm]
apn=internet2.voicestream.com
device-id=da812de91eec16620b06cd0ca5cbc7ea25245222
home-only=true
network-id=254098
password=parliament2
pin=123456
sim-id=89148000000060671234
sim-operator-id=310260
username=george.clinton.again

[ipv4]
dns-search=
method=auto

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
method=auto
'''
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  modems:
    NM-{}:
      renderer: NetworkManager
      match: {{}}
      apn: "internet2.voicestream.com"
      device-id: "da812de91eec16620b06cd0ca5cbc7ea25245222"
      network-id: "254098"
      pin: "123456"
      sim-id: "89148000000060671234"
      sim-operator-id: "310260"
      networkmanager:
        uuid: {}
        name: "T-Mobile Funkadelic 2"
        passthrough:
          gsm.home-only: "true"
          gsm.password: "parliament2"
          gsm.username: "george.clinton.again"
          ipv4.dns-search: ""
          ipv4.method: "auto"
          ipv6.addr-gen-mode: "stable-privacy"
          ipv6.dns-search: ""
          ipv6.method: "auto"
'''.format(UUID, UUID))

    def test_serialize_gsm_via_bluetooth(self):
        self.maxDiff = None
        UUID = 'a08c5805-7cf5-43f7-afb9-12cb30f6eca3'
        file = '''[connection]
id=T-Mobile Funkadelic 2
uuid=a08c5805-7cf5-43f7-afb9-12cb30f6eca3
type=bluetooth

[gsm]
apn=internet2.voicestream.com
device-id=da812de91eec16620b06cd0ca5cbc7ea25245222
home-only=true
network-id=254098
password=parliament2
pin=123456
sim-id=89148000000060671234
sim-operator-id=310260
username=george.clinton.again

[ipv4]
dns-search=
method=auto

[ipv6]
addr-gen-mode=stable-privacy
dns-search=
method=auto

[proxy]
'''
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  others:
    NM-{}:
      renderer: NetworkManager
      networkmanager:
        uuid: {}
        name: "T-Mobile Funkadelic 2"
        passthrough:
          connection.type: "bluetooth"
          gsm.apn: "internet2.voicestream.com"
          gsm.device-id: "da812de91eec16620b06cd0ca5cbc7ea25245222"
          gsm.home-only: "true"
          gsm.network-id: "254098"
          gsm.password: "parliament2"
          gsm.pin: "123456"
          gsm.sim-id: "89148000000060671234"
          gsm.sim-operator-id: "310260"
          gsm.username: "george.clinton.again"
          ipv4.dns-search: ""
          ipv4.method: "auto"
          ipv6.addr-gen-mode: "stable-privacy"
          ipv6.dns-search: ""
          ipv6.method: "auto"
          proxy._: ""
'''.format(UUID, UUID))

    def _template_serialize_keyfile(self, nd_type, nm_type, supported=True):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '[connection]\ntype={}\nuuid={}'.format(nm_type, UUID)
        self.assertEqual(lib.netplan_clear_netdefs(), 0)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        t = '\n        passthrough:\n          connection.type: "{}"'.format(nm_type) if not supported else ''
        match = '\n      match: {}' if nd_type in ['ethernets', 'modems', 'wifis'] else ''
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  {}:
    NM-{}:
      renderer: NetworkManager{}
      networkmanager:
        uuid: {}{}
'''.format(nd_type, UUID, match, UUID, t))

    def test_serialize_keyfile_ethernet(self):
        self._template_serialize_keyfile('ethernets', 'ethernet')

    def test_serialize_keyfile_type_modem_gsm(self):
        self._template_serialize_keyfile('modems', 'gsm')

    def test_serialize_keyfile_type_modem_cdma(self):
        self._template_serialize_keyfile('modems', 'cdma')

    def test_serialize_keyfile_type_bridge(self):
        self._template_serialize_keyfile('bridges', 'bridge')

    def test_serialize_keyfile_type_bond(self):
        self._template_serialize_keyfile('bonds', 'bond')

    def test_serialize_keyfile_type_vlan(self):
        self._template_serialize_keyfile('vlans', 'vlan')

    def test_serialize_keyfile_type_tunnel(self):
        self._template_serialize_keyfile('tunnels', 'ip-tunnel', False)

    def test_serialize_keyfile_type_wireguard(self):
        self._template_serialize_keyfile('tunnels', 'wireguard', False)

    def test_serialize_keyfile_type_other(self):
        self._template_serialize_keyfile('others', 'dummy', False)

    def test_serialize_keyfile_missing_uuid(self):
        file = '[connection]\ntype=ethernets'
        self.assertFalse(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))

    def test_serialize_keyfile_missing_type(self):
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '[connection]\nuuid={}'.format(UUID)
        self.assertFalse(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))

    def test_serialize_keyfile_type_wifi(self):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]
type=wifi
uuid={}
permissions=
id=myid with spaces
interface-name=eth0

[wifi]
ssid=SOME-SSID
mode=infrastructure
hidden=true

[ipv4]
method=auto
dns-search='''.format(UUID)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  wifis:
    NM-{}:
      renderer: NetworkManager
      match:
        name: "eth0"
      access-points:
        "SOME-SSID":
          hidden: true
          mode: infrastructure
          networkmanager:
            uuid: {}
            name: "myid with spaces"
            passthrough:
              connection.permissions: ""
              ipv4.method: "auto"
              ipv4.dns-search: ""
      networkmanager:
        uuid: {}
        name: "myid with spaces"
'''.format(UUID, UUID, UUID))

    def _template_serialize_keyfile_type_wifi(self, nd_mode, nm_mode):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]
type=wifi
uuid={}
id=myid with spaces

[ipv4]
method=auto

[wifi]
ssid=SOME-SSID
mode={}'''.format(UUID, nm_mode)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        wifi_mode = ''
        if nm_mode != nd_mode:
            wifi_mode = '\n              wifi.mode: "{}"'.format(nm_mode)
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  wifis:
    NM-{}:
      renderer: NetworkManager
      match: {{}}
      access-points:
        "SOME-SSID":
          mode: {}
          networkmanager:
            uuid: {}
            name: "myid with spaces"
            passthrough:
              ipv4.method: "auto"{}
      networkmanager:
        uuid: {}
        name: "myid with spaces"
'''.format(UUID, nd_mode, UUID, wifi_mode, UUID))

    def test_serialize_keyfile_type_wifi_ap(self):
        self._template_serialize_keyfile_type_wifi('ap', 'ap')

    def test_serialize_keyfile_type_wifi_adhoc(self):
        self._template_serialize_keyfile_type_wifi('adhoc', 'adhoc')

    def test_serialize_keyfile_type_wifi_unknown(self):
        self._template_serialize_keyfile_type_wifi('infrastructure', 'mesh')

    def test_serialize_keyfile_type_wifi_missing_ssid(self):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]\ntype=wifi\nuuid={}\nid=myid with spaces'''.format(UUID)
        self.assertFalse(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertFalse(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))

    def test_serialize_keyfile_wake_on_lan(self):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]
type=ethernet
uuid={}
id=myid with spaces

[ethernet]
wake-on-lan=2

[ipv4]
method=auto'''.format(UUID)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  ethernets:
    NM-{}:
      renderer: NetworkManager
      match: {{}}
      wakeonlan: true
      networkmanager:
        uuid: {}
        name: "myid with spaces"
        passthrough:
          ethernet.wake-on-lan: "2"
          ipv4.method: "auto"
'''.format(UUID, UUID))

    def test_serialize_keyfile_wake_on_lan_nm_default(self):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]
type=ethernet
uuid={}
id=myid with spaces

[ethernet]

[ipv4]
method=auto'''.format(UUID)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  ethernets:
    NM-{}:
      renderer: NetworkManager
      match: {{}}
      wakeonlan: true
      networkmanager:
        uuid: {}
        name: "myid with spaces"
        passthrough:
          ethernet._: ""
          ipv4.method: "auto"
'''.format(UUID, UUID))

    def test_serialize_keyfile_modem_gsm(self):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]
type=gsm
uuid={}
id=myid with spaces

[ipv4]
method=auto

[gsm]
auto-config=true'''.format(UUID)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), None, self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  modems:
    NM-{}:
      renderer: NetworkManager
      match: {{}}
      auto-config: true
      networkmanager:
        uuid: {}
        name: "myid with spaces"
        passthrough:
          ipv4.method: "auto"
'''.format(UUID, UUID))

    def test_serialize_keyfile_existing_id(self):
        self.maxDiff = None
        UUID = '87749f1d-334f-40b2-98d4-55db58965f5f'
        file = '''[connection]
type=bridge
uuid={}
id=renamed netplan bridge

[ipv4]
method=auto'''.format(UUID)
        self.assertTrue(lib._netplan_render_yaml_from_nm_keyfile_str(file.encode(), "mybr".encode(), self.workdir.name.encode()))
        self.assertTrue(os.path.isfile(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID))))
        with open(os.path.join(self.confdir, '90-NM-{}.yaml'.format(UUID)), 'r') as f:
            self.assertEqual(f.read(), '''network:
  version: 2
  bridges:
    mybr:
      renderer: NetworkManager
      networkmanager:
        uuid: {}
        name: "renamed netplan bridge"
        passthrough:
          ipv4.method: "auto"
'''.format(UUID))
