#!/usr/bin/env python3

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
from json import loads
import sys
airbag.enable()


sla_config = '/tmp/sla.conf'

def get_config(config=None):
    if config:
        conf = config
    else:
        conf = Config()
    sdwan = conf.get_config_dict("sdwan")
    try:
        return sdwan['sdwan']
    except KeyError:
        return {}

def verify(underlay):
    return None

def generate(underlay):
    return None

def apply(sdwan, operation):
    is_deleted = operation == "delete"
    if not os.path.exists(sla_config):
        subprocess.run(['sudo', 'touch', '/tmp/sla.conf'], capture_output=False)
    underlays = sdwan.get('underlay', {}) if sdwan else {}
    for underlay_name, underlay_config in underlays.items():
        if is_deleted:
            try:
                with open(sla_config, 'r') as json_file:
                    existing_data = json.load(json_file)
                existing_data.pop(underlay_name)
                with open(sla_config, 'w') as json_file:
                    json.dump(existing_data, json_file, indent=4)
                restart = subprocess.run(['sudo', 'systemctl', 'restart', 'sdwan-sla'], capture_output=True)
            except Exception as e:
                return None
        else:
            sla_profile = underlay_config.get('sla-profile')
            if sla_profile:
                sla_profile_main= sdwan['sla-profiles'].get(sla_profile)
                if sla_profile_main:
                    underlay_config['sla'] = sdwan['sla-profiles'][sla_profile]
                    result = {underlay_name: underlay_config}
                    try:
                        with open(sla_config, 'r') as json_file:
                            existing_data = json.load(json_file)
                    except:
                        existing_data = {}
                    existing_data[underlay_name] = underlay_config
                    with open(sla_config, 'w') as json_file:
                        json.dump(existing_data, json_file, indent=4)
                    restart = subprocess.run(['sudo', 'systemctl', 'restart', 'sdwan-sla'], capture_output=True)
                else:
                    raise ConfigError(f"Error: Please configure the SLA profile using 'set sdwan sla-profiles {sla_profile} ...'")
    return None

if __name__ == '__main__':
    try:
        operation = sys.argv[1] if len(sys.argv) > 1 else "set"
        sdwan = get_config()
        verify(sdwan)
        generate(sdwan)
        apply(sdwan, operation)
    except ConfigError as e:
        print(e)
        exit(1)
