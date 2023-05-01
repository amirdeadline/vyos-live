#!/usr/bin/env python3
#
# Copyright (C) 2021 VyOS maintainers and contributors
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 or later as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from netifaces import interfaces
from sys import exit

from vyos.config import Config
from vyos.configdict import get_interface_dict
from vyos.configverify import verify_mirror_redirect
from vyos.ifconfig import VTIIf
from vyos.util import dict_search
from vyos.template import render
from vyos import ConfigError
from vyos import airbag
from vyos.util import call
import json
import subprocess
import os 

airbag.enable()

service_name = 'delta-sla'
# service_conf = Path(f'/run/{service_name}.conf')
systemd_service = '/run/systemd/system/delta-sla.service'
sla_config = '/tmp/sla.conf'


def get_config(config=None):
    """
    Retrive CLI config as dictionary. Dictionary can never be empty, as at least the
    interface name will be added or a deleted flag
    """
    if config:
        conf = config
    else:
        conf = Config()
    base = ['interfaces', 'vti']
    _, vti = get_interface_dict(conf, base)
    sdwan = conf.get_config_dict("sdwan")
    return vti, sdwan

def verify(vti):
    verify_mirror_redirect(vti)
    return None

def generate(vti):
    return None

def apply(vti, sdwan):
    if not os.path.exists(sla_config):
        subprocess.run(['sudo', 'touch', '/tmp/sla.conf'], capture_output=False)
    if 'deleted' in vti:
        VTIIf(**vti).remove()
        try:
            with open(sla_config, 'r') as json_file:
                existing_data = json.load(json_file)
            existing_data.pop(vti['ifname'])
            with open(sla_config, 'w') as json_file:
                json.dump(existing_data, json_file, indent=4)
            restart = subprocess.run(['sudo', 'systemctl', 'restart', 'sdwan-sla'], capture_output=True)            
        except Exception as e:
            print(f"Could not remove interface {e} from SDWNAN datebase")
            return None
        return None
    else:
        sla_profile = vti.get('sla_profile')
        print(vti['sla_profile'], sla_profile)
        if sla_profile:
            sla_profile_main= sdwan["sdwan"]['sla-profiles'].get(sla_profile)
            if sla_profile_main:
                vti['sla'] = sdwan["sdwan"]['sla-profiles'][sla_profile]
                result = {vti['ifname']: vti}
                try:
                    with open(sla_config, 'r') as json_file:
                        existing_data = json.load(json_file)
                except:
                    existing_data = {}
                existing_data[vti['ifname']] = vti
                print(vti)
                with open(sla_config, 'w') as json_file:
                    json.dump(existing_data, json_file, indent=4)
                restart = subprocess.run(['sudo', 'systemctl', 'restart', 'sdwan-sla'], capture_output=True)         
            else:
                raise(f"Error: Please configure the SLA profile using 'set sdwan sla-profiles {sla_profile} ...'")
    tmp = VTIIf(**vti)
    tmp.update(vti)
    return None

if __name__ == '__main__':
    try:
        c,sdwan = get_config()
        verify(c)
        generate(c)
        apply(c, sdwan)
    except ConfigError as e:
        print(e)
        exit(1)
