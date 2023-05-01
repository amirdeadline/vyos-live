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
import sys
airbag.enable()


vyos_tagnode_value = os.environ.get("VYOS_TAGNODE_VALUE", None)

sla_config = "/tmp/sla.conf"
def update_sla_config(sla_config, sla_profile, sla_data):
    with open(sla_config, "r") as f:
        config_data = json.load(f)
    # Find interfaces with the specified SLA profile and update their SLA configuration
    updated = False
    for vti_interface, interface_data in config_data.items():
        if interface_data.get("sla_profile") == sla_profile:
            if interface_data["sla"] != sla_data:
                interface_data["sla"] = sla_data
                updated = True
    if updated:
        # Write the updated configuration to the JSON file
        with open(sla_config, "w") as f:
            json.dump(config_data, f, indent=4)
        return True
    return False
def get_config(config=None):
    """
    Retrive CLI config as dictionary.
    """
    try:
        conf = Config()
        base = ['sdwan','sla-profiles']
        sla = conf.get_config_dict(base)
        return sla
    except Exception as e:
        print("Error: Could not get SLA configurations\n", e)

def verify(sla):
    return None

def generate(sla):
    return None


def apply(sla, operation):
    is_deleted = operation == "delete"
    # print(is_deleted, sla)
    if is_deleted:
        if os.path.exists(sla_config):
            with open(sla_config, 'r') as json_file:
                existing_data = json.load(json_file)
            for vti in existing_data:
                if existing_data[vti]['sla_profile'] == vyos_tagnode_value:
                    raise ConfigError(f"Error, SLA Profile is in use on VTI {vti}")
        else:
            return None
    elif vyos_tagnode_value:
        try:
            config = sla['sla-profiles'][vyos_tagnode_value]
            update_sla_config(sla_config, vyos_tagnode_value, config)
        except:
            pass
    return None



if __name__ == '__main__':
    try:
        operation = sys.argv[1] if len(sys.argv) > 1 else "set"
        c = get_config()
        verify(c)
        generate(c)
        apply(c, operation)
    except ConfigError as e:
        print(e)
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)
