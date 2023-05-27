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
import subprocess

from vyos.config import Config
from vyos.configdict import get_interface_dict
from vyos.configverify import verify_mirror_redirect
from vyos.ifconfig import VTIIf
from vyos.util import dict_search
from jinja2 import Template, Environment, FileSystemLoader
from vyos import ConfigError
from vyos import airbag
from vyos.util import call
import json
import subprocess
import os
import sys
airbag.enable()

from jinja2 import Template

nftables_conf = '/run/nftables_sdwan.conf'
template= '/usr/share/vyos/templates/sdwan/symmetric_nftable.j2'

def get_config(config=None):
    """
    Retrive CLI config as dictionary.
    """
    result={}
    try:
        conf = Config()
        result['interfaces']=conf.get_config_dict(["interfaces"])
        result['sdwan']=conf.get_config_dict(["sdwan"])
        result['vrf']=conf.get_config_dict(["vrf"])
        return result
    except Exception as e:
        print("Error: Could not get SLA configurations\n", e)


def check_nft_table(table_name):
    try:
        output = subprocess.check_output(['sudo', 'nft', 'list', 'ruleset'], universal_newlines=True)
        print(output)
        if f'table {table_name}' in output:
            print(f'Table {table_name} exists.')
        else:
            print(f'Table {table_name} does not exist.')
    except subprocess.CalledProcessError as e:
        print(f'An error occurred while checking the table: {str(e)}')
        

def assign_meta_marks(interfaces, start=2147800000):
    for interface in interfaces:
        interfaces[interface]['meta_marks'] = start
        start += 1
    return interfaces


def parse_interfaces(config):
    interfaces={'lan':{}, 'internet':{}, 'private-underlay':{}, 'overlay':{}, 'vpn':{},
     'v-lan':{}, 'v-internet':{}, 'v-overlay':{}, 'v-private-underlay':{}}

    for key, value in config['interfaces']['interfaces'].items():
        for key1 , value1 in value.items():
            if 'role' in value1:
                interfaces[value1['role']][key1]=value1
                if value1['role']=='overlay' and key1[:3]=='vti':
                    interfaces[value1['role']][key1]['mark']=key1[3::]
    interfaces['overlay'] = assign_meta_marks(interfaces['overlay'], 2147800000)
    return interfaces

def generate(interfaces, template, output_file):
    # Create Jinja2 environment with the template directory
    template_dir = os.path.dirname(template)
    env = Environment(loader=FileSystemLoader(template_dir))
    # Load the template
    template = env.get_template(os.path.basename(template))
    # Render nftables configuration
    rendered_config = template.render(interfaces=interfaces)
    # Save nftables configuration to file
    with open(output_file, "w") as file:
        file.write(rendered_config)

# Generate VTYSH configuration for ip routes
def create_tables(overlays):
    vtysh_config = ""
    for interface in overlays:
        table_id = overlays[interface]['mark']
        vtysh_config += f"ip route 0.0.0.0/0 {interface} nexthop-vrf CTRL table {table_id}\n"
    # Apply VTYSH configuration
    os.system("vtysh -c 'configure terminal' -c '{}'".format(vtysh_config))

def route_rules(overlays):
    for interface in overlays:
        table_id = overlays[interface]['mark']
        fwmark = hex(overlays[interface]['meta_marks'])
        rules_config = f"sudo ip rule add pref 20 fwmark {fwmark} table {table_id}\n"
       # Apply VTYSH configuration
        os.system(rules_config)

def apply(interfaces, operation):
    create_tables(interfaces['overlay'])
    route_rules(interfaces['overlay'])
    # Apply nftables configuration
    os.system(f"/sbin/nft -f {nftables_conf}")

def check_and_delete_table():
    table_name = "delta_symmetric"

    # Check if the table exists
    cmd_exists = f"sudo nft list tables | grep -w {table_name}"
    exists_process = subprocess.run(cmd_exists, shell=True, capture_output=True, text=True)
    table_exists = (exists_process.returncode == 0)

    # Delete the table if it exists
    if table_exists:
        cmd_delete = f"sudo nft delete table ip {table_name}"
        subprocess.run(cmd_delete, shell=True)
        print(f"The '{table_name}' NFT table has been deleted.")
    else:
        print(f"The '{table_name}' NFT table does not exist.")

def delete(interfaces):
    check_and_delete_table()
    if os.path.exists(nftables_conf):
        os.remove(nftables_conf)
    for interface, value in interfaces['overlay'].items():
        fwmark = hex(value['meta_marks'])
        try:
            os.system(f"sudo ip rule delete pref 20 fwmark {fwmark}")
        except:
            pass
        try:
            os.system(f"vtysh -c 'configure terminal' -c 'no ip route 0.0.0.0/0 {interface} nexthop-vrf CTRL table {value['mark']}'")
        except:
            pass
            
if __name__ == '__main__':
    try:
        operation = sys.argv[1] if len(sys.argv) > 1 else "set"
        c = get_config()
        interfaces = parse_interfaces(c)
        if operation=='delete':
            delete(interfaces)
        elif operation=='reset':
            if 'symmetric-forwarding' in c['sdwan']['sdwan']['options']:
                try:
                    delete(interfaces)
                except:
                    pass
                generate(interfaces, template,  nftables_conf)
                apply(interfaces, operation)
            else:
                print("The symmetric-forwarding is not set under SDWAN options")
        else:
            if os.path.exists(nftables_conf):
                os.system(f"sudo nft delete table ip delta_symmetric")
                os.remove(nftables_conf)
            generate(interfaces, template,  nftables_conf)
            apply(interfaces, operation)

    except ConfigError as e:
        print(e)
        exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        exit(1)