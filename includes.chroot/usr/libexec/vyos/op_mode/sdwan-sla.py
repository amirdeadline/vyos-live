#!/usr/bin/env python3

import json
import sys
import redis
import subprocess
import time
from tabulate import tabulate
import vyos.opmode
from vyos.ifconfig import Section
from vyos.ifconfig import Interface
from vyos.ifconfig import VRRP
from vyos.util import cmd, rc_cmd, call, convert_data, seconds_to_human
from vyos.config import Config
from vyos.configquery import ConfigTreeQuery
import yaml
import vyos.opmode
import vyos.ipsec
from vyos.util import cmd, rc_cmd, call
from interfaces import _get_raw_data, show
import re
import typing
import datetime


sla_config = "/tmp/sla.conf"

def get_config(base):
    """
    Retrive CLI config as dictionary.
    """
    try:
        conf = Config()
        c = conf.get_config_dict(base)
        return c
    except Exception as e:
        print(f"Error: Could not get {base} configurations\n", e)

def _get_summary_data(ifname: typing.Optional[str],
                      iftype: typing.Optional[str],
                      vif: bool, vrrp: bool) -> list:
    if ifname is None:
        ifname = ''
    if iftype is None:
        iftype = ''
    ret = []
    for interface in filtered_interfaces(ifname, iftype, vif, vrrp):
        res_intf = {}

        res_intf['ifname'] = interface.ifname
        res_intf['oper_state'] = interface.operational.get_state()
        res_intf['admin_state'] = interface.get_admin_state()
        res_intf['addr'] = [_ for _ in interface.get_addr() if not _.startswith('fe80::')]
        res_intf['description'] = interface.get_alias()

        ret.append(res_intf)

    # find pppoe interfaces that are in a transitional/dead state
    if ifname.startswith('pppoe') and not _find_intf_by_ifname(ret, ifname):
        pppoe_intf = {}
        pppoe_intf['unhandled'] = None
        pppoe_intf['ifname'] = ifname
        pppoe_intf['state'] = _pppoe(ifname)
        ret.append(pppoe_intf)

    return ret

def _get_counter_val(prev, now):
    """
    attempt to correct a counter if it wrapped, copied from perl

    prev: previous counter
    now:  the current counter
    """
    # This function has to deal with both 32 and 64 bit counters
    if prev == 0:
        return now

    # device is using 64 bit values assume they never wrap
    value = now - prev
    if (now >> 32) != 0:
        return value

    # The counter has rolled.  If the counter has rolled
    # multiple times since the prev value, then this math
    # is meaningless.
    if value < 0:
        value = (4294967296 - prev) + now

    return value

def filtered_interfaces(ifnames: typing.Union[str, list],
                        iftypes: typing.Union[str, list],
                        vif: bool, vrrp: bool):
    """
    get all interfaces from the OS and return them; ifnames can be used to
    filter which interfaces should be considered

    ifnames: a list of interface names to consider, empty do not filter

    return an instance of the Interface class
    """
    if isinstance(ifnames, str):
        ifnames = [ifnames] if ifnames else []
    if isinstance(iftypes, list):
        for iftype in iftypes:
            yield from filtered_interfaces(ifnames, iftype, vif, vrrp)

    for ifname in Section.interfaces(iftypes):
        # Bail out early if interface name not part of our search list
        if ifnames and ifname not in ifnames:
            continue

        # As we are only "reading" from the interface - we must use the
        # generic base class which exposes all the data via a common API
        interface = Interface(ifname, create=False, debug=False)

        # VLAN interfaces have a '.' in their name by convention
        if vif and not '.' in ifname:
            continue

        if vrrp:
            vrrp_interfaces = VRRP.active_interfaces()
            if ifname not in vrrp_interfaces:
                continue

        yield interface


def get_vti_interfaces_from_redis():
    r = redis.Redis()
    vti_interfaces = r.keys("vti*_sla_status")
    return [vti.decode().replace('_sla_status', '') for vti in vti_interfaces]

def get_data_from_redis(vti_interface):
    r = redis.Redis()
    keys = [f"{vti_interface}_{metric}" for metric in ["packetloss", "delay", "jitter", "MOS", "sla_status"]]
    values = [r.get(key).decode() if r.get(key) is not None else "N/A" for key in keys]
    status = "UP" if values[-1] == "1" else "DOWN"
    return values[:-1] + [status]

def read_sla_config():
    with open(sla_config, "r") as f:
        return json.load(f)

def sla_status(peer: str):
    vti_interface= peer
    sla_config_data = read_sla_config()
    headers=['VTI\ninterface', 'Local\nCircuit','Remote\nSite','Remote\nCircuit', 'Packet\nLoss (%)', 'Delay\n(ms)','Jitter\n(ms)','MOS\nScore','\nStatus','\nLast Change' ]
    config = sla_config_data.get(vti_interface)
    if config:
        local_circuit = config.get("local_circuit", "N/A")
        remote_site = config.get("remote_site", "N/A")
        remote_circuit = config.get("remote_circuit", "N/A")
        packetloss, delay, jitter, mos, status = get_data_from_redis(vti_interface)
        last_change= get_last_change(vti_interface)
        row = [vti_interface, local_circuit, remote_site, remote_circuit, packetloss, delay, jitter, mos, status, last_change]
        output = tabulate([row], headers, stralign="left", numalign="left")
    else:
        output= f"Could not find {vti_interface}"
    return output


def sla_status_summary():
    vti_interfaces = get_vti_interfaces_from_redis()
    sla_data = []
    sla_config_data = read_sla_config()

    headers=['VTI\nninterface', 'Local\nCircuit','Remote\nSite','Remote\nCircuit', 'Packet\nLoss (%)', 'Delay\n(ms)','Jitter\n(ms)','MOS\nScore','\nStatus','\nLast Change' ]

    for vti_interface in vti_interfaces:
        config = sla_config_data.get(vti_interface)
        if config:
            local_circuit = config.get("local_circuit", "N/A")
            remote_site = config.get("remote_site", "N/A")
            remote_circuit = config.get("remote_circuit", "N/A")

            packetloss, delay, jitter, mos, status = get_data_from_redis(vti_interface)
            last_change= get_last_change(vti_interface)
            row = [vti_interface, local_circuit, remote_site, remote_circuit, packetloss, delay, jitter, mos, status, last_change]
            sla_data.append(row)

    output = tabulate(sla_data, headers, stralign="left", numalign="left")
    return output

def _get_counter_data(ifname: typing.Optional[str],
                      iftype: typing.Optional[str],
                      vif: bool, vrrp: bool) -> list:
    if ifname is None:
        ifname = ''
    if iftype is None:
        iftype = ''
    ret = []
    for interface in filtered_interfaces(ifname, iftype, vif, vrrp):
        res_intf = {}

        oper = interface.operational.get_state()

        if oper not in ('up','unknown'):
            continue

        stats = interface.operational.get_stats()
        cache = interface.operational.load_counters()
        res_intf['ifname'] = interface.ifname
        res_intf['rx_packets'] = _get_counter_val(cache['rx_packets'], stats['rx_packets'])
        res_intf['rx_bytes'] = _get_counter_val(cache['rx_bytes'], stats['rx_bytes'])
        res_intf['tx_packets'] = _get_counter_val(cache['tx_packets'], stats['tx_packets'])
        res_intf['tx_bytes'] = _get_counter_val(cache['tx_bytes'], stats['tx_bytes'])

        ret.append(res_intf)

    return ret

def show(raw: bool, intf_name: typing.Optional[str],
                    intf_type: typing.Optional[str],
                    vif: bool, vrrp: bool):
    data = _get_raw_data(intf_name, intf_type, vif, vrrp)
    if raw:
        return data
    return _format_show_data(data)

def show_counters(raw: bool, intf_name: typing.Optional[str],
                             intf_type: typing.Optional[str],
                             vif: bool, vrrp: bool):
    data = _get_counter_data(intf_name, intf_type, vif, vrrp)
    if raw:
        return data
    return _format_show_counters(data)

def show_sa(raw: bool):
    sa_data = _get_raw_data_sas()
    if raw:
        return sa_data
    return _get_formatted_output_sas(sa_data)

def _get_raw_data_sas():
    try:
        get_sas = vyos.ipsec.get_vici_sas()
        sas = convert_data(get_sas)
        return sas
    except (vyos.ipsec.ViciInitiateError) as err:
        raise vyos.opmode.UnconfiguredSubsystem(err)

def overlay(peer: str):
    vti= "vti"+peer
    output = subprocess.check_output(['vtysh', '-c', 'show ip ospf vrf CTRL neighbor']).decode('utf-8')
    interface_output = subprocess.check_output(['vtysh', '-c', 'show interface '+vti]).decode('utf-8')
    interface_output2 = show(intf_name=vti, intf_type='vti', raw=True, vif=False, vrrp=False)
    ipsec= _get_raw_data_sas()
    ipsec_output={}
    try:
        for d in ipsec:
                key = list(filter(lambda k: k.isnumeric(), d.keys()))[0]
                ipsec_output[key] = d[key]
    except IndexError:
        print("[[ There is No SDWAN overlay provisioned. Also make sure IPSEC Peer Names are Integer]]\n")

    sla_config = read_sla_config()  # Assuming this function is defined elsewhere
    neighbors = {}
    for line in output.splitlines():
        match = re.search(r'^(\S+)\s+(\d+)\s+(\S+\/\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line)

        if match:
            neighbor_id, priority, state, uptime, deadtime, address, interface, metrics = match.groups()
            vti_interface = interface.split(':')[0]

            if vti_interface not in neighbors:
                neighbors[vti_interface] = {}

            neighbors[vti_interface] = {
                'neighbor_id': neighbor_id,
                'address': address,
                'priority': priority,
                'state': state,
                'uptime': uptime,
                'deadtime': deadtime,
                'interface': interface,
                'rxmtl': metrics.split()[0],
                'rqstl': metrics.split()[1],
                'dbsml': metrics.split()[2]
            }
            
            if neighbors[vti_interface]['state'] == 'Full/-':
                neighbors[vti_interface]['status'] = 'UP'
            else:
                neighbors[vti_interface]['status'] = 'DOWN'
    headers = ["Overlay\nID","Remote\nSite", "Remote\nCircuit", "Local\nCircuit", "SLA\nStatus", "Overlay\nStatus", "Local\nAddr", "Remote\nAddr"]
    result_lines = []
    try:
        remote = sla_config[vti].get('remote_site')
        result = []
        if remote:
            result.append(vti[3::])
            result.append(sla_config[vti]['remote_site'])
            result.append(sla_config[vti]['remote_circuit'])
            result.append(sla_config[vti]['local_circuit'])
            packetloss, delay, jitter, mos, status = get_data_from_redis(vti)
            result.append(status)
            result.append(neighbors.get(vti, {}).get('status', 'DOWN'))
            try:
                remote_addr= ipsec_output[vti[3::]]['remote-host']+":"+ipsec_output[vti[3::]]['remote-port']
                local_addr= ipsec_output[vti[3::]]['local-host']+":"+ipsec_output[vti[3::]]['local-port']
            except:
                local_addr='-'
                remote_addr='-'

            result.append(local_addr)  
            result.append(remote_addr) 
            result_lines.append(result)
    except:
        print(f"Error: Peer Name configured for SDWAN tunnel {vti} is wrong. It should be {vti[3::]}")

    del interface_output2[0]["flags"]
    del interface_output2[0]["group"]
    del interface_output2[0]["link"]
    del interface_output2[0]["link_type"]
    interface_output2[0]["vrf"] = interface_output2[0]["master"]
    del interface_output2[0]["master"]
    del interface_output2[0]["qdisc"]

    packetloss, delay, jitter, mos, status = get_data_from_redis(vti_interface)
    header2= ["Packet Loss", "Delay ", "jitter", "MOS SCORE", "SLA STATUS" ]
    output = tabulate(result_lines, headers, stralign="left", numalign="left") + "\n\n"
    output+= tabulate([[packetloss, delay, jitter, mos, status]], header2, stralign="left", numalign="left") + "\n\n" + (40*"#") + " VTI STATUS " + (41*"#") +"\n"
    output+= yaml.dump(interface_output2[0], default_flow_style=False) +  "\n" + (40*"#") + " OSPF STATUS " + (40*"#") +"\n"
    output+= yaml.dump(neighbors[vti], default_flow_style=False)
    return output

def overlay_summary():
    output = subprocess.check_output(['vtysh', '-c', 'show ip ospf vrf CTRL neighbor']).decode('utf-8')
    ipsec= _get_raw_data_sas()
    ipsec_output={}
    try:
        for d in ipsec:
                key = list(filter(lambda k: k.isnumeric(), d.keys()))[0]
                ipsec_output[key] = d[key]
    except IndexError:
        print("[[ There is No SDWAN overlay provisioned. Also make sure IPSEC Peer Names are Integer]]\n")

    sla_config = read_sla_config()  # Assuming this function is defined elsewhere
    neighbors = {}
    for line in output.splitlines():
        match = re.search(r'^(\S+)\s+(\d+)\s+(\S+\/\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(.+)$', line)

        if match:
            neighbor_id, priority, state, uptime, deadtime, address, interface, metrics = match.groups()
            vti_interface = interface.split(':')[0]

            if vti_interface not in neighbors:
                neighbors[vti_interface] = {}

            neighbors[vti_interface] = {
                'neighbor_id': neighbor_id,
                'address': address,
                'priority': priority,
                'state': state,
                'uptime': uptime,
                'deadtime': deadtime,
                'interface': interface,
                'rxmtl': metrics.split()[0],
                'rqstl': metrics.split()[1],
                'dbsml': metrics.split()[2]
            }
            
            if neighbors[vti_interface]['state'] == 'Full/-':
                neighbors[vti_interface]['status'] = 'UP'
            else:
                neighbors[vti_interface]['status'] = 'DOWN'
    headers = ["Overlay\nID","Remote\nSite", "Remote\nCircuit", "Local\nCircuit", "SLA\nStatus", "Overlay\nStatus", "Local\nAddr", "Remote\nAddr"]
    result_lines = []
    for vti in sla_config:
        try:
            remote = sla_config[vti].get('remote_site')
            result = []
            if remote:
                result.append(vti[3::])
                result.append(sla_config[vti]['remote_site'])
                result.append(sla_config[vti]['remote_circuit'])
                result.append(sla_config[vti]['local_circuit'])
                packetloss, delay, jitter, mos, status = get_data_from_redis(vti)
                
                result.append(status)
                result.append(neighbors.get(vti, {}).get('status', 'DOWN'))
                try:
                    remote_addr= ipsec_output[vti[3::]]['remote-host']+":"+ipsec_output[vti[3::]]['remote-port']
                    local_addr= ipsec_output[vti[3::]]['local-host']+":"+ipsec_output[vti[3::]]['local-port']
                except:
                    local_addr='-'
                    remote_addr='-'

                result.append(local_addr)  
                result.append(remote_addr) 
                result_lines.append(result)
        except:
            print(f"Error: Peer Name configured for SDWAN tunnel {vti} is wrong. It should be {vti[3::]}")

    output = tabulate(result_lines, headers, stralign="left", numalign="left")
    return output


def get_sdwan_config():
    """
    Retrive CLI config as dictionary.
    """
    try:
        conf = Config()
        base = ['sdwan']
        sdwan = conf.get_config_dict(base)
        return sdwan['sdwan']
    except Exception as e:
        print("Error: Could not get SDWAN configurations\n", e)

def underlay_summary():
    sdwan = get_sdwan_config()
    rows=[]
    headers=['Underlay\nName', 'Underlay\nID','Transpot\nID','ISP', 'Packet\nLoss (%)', 'Delay\n(ms)','Jitter\n(ms)','\nStatus' ,'\nLast Change' ]
    for i in sdwan['underlay']:
        if sdwan['underlay'][i]['transport-id']=="0":
            packetloss, delay, jitter, mos, status = get_data_from_redis(i)
            last_change= get_last_change(i)
            print(last_change)
            row=[i, 
            sdwan['underlay'][i]['underlay-id'],
            "0/Internet" ,
            sdwan['underlay'][i]['service-provider'], 
            packetloss, delay, jitter, status,last_change]
            rows.append(row)
        else:
            packetloss, delay, jitter, mos, status = "-", "-", "-", "-", "-"
            last_change= get_last_change(i)
            row=[i, 
            sdwan['underlay'][i]['underlay-id'],
            sdwan['underlay'][i]['transport-id'], 
            sdwan['underlay'][i]['service-provider'], 
            packetloss, delay, jitter, status,last_change]
            rows.append(row)
    output = tabulate(rows, headers, stralign="left", numalign="left")
    return output

def underlay(peer: str):
    i=peer
    sdwan = get_sdwan_config()
    headers=['Underlay\nName', 'Underlay\nID','Transpot\nID','ISP', 'Packet\nLoss (%)', 'Delay\n(ms)','Jitter\n(ms)','\nStatus','\nLast Change' ]
    if sdwan['underlay'][i]['transport-id']=="0":
        packetloss, delay, jitter, mos, status = get_data_from_redis(i)
        last_change= get_last_change(i)
        row=[i, 
        sdwan['underlay'][i]['underlay-id'],
        "0/Internet" ,
        sdwan['underlay'][i]['service-provider'], 
        packetloss, delay, jitter, status,last_change]
    else:
        packetloss, delay, jitter, mos, status = "-", "-", "-", "-", "-"
        last_change= get_last_change(i)
        row=[i, 
        sdwan['underlay'][i]['underlay-id'],
        sdwan['underlay'][i]['transport-id'], 
        sdwan['underlay'][i]['service-provider'], 
        packetloss, delay, jitter, status,last_change]
    output = tabulate([row], headers, stralign="left", numalign="left")
    return output

def get_last_change(sla):
    r = redis.Redis(host='localhost', port=6379, db=0)
    last_change_key = f"{sla}_last_change"
    last_change_value = r.get(last_change_key)
    if last_change_value is not None:
        return last_change_value.decode()
    else:
        return None

def delete_redis_keys(filter_pattern):
    r = redis.Redis()
    keys = r.keys(filter_pattern)
    for key in keys:
        r.delete(key)

def clear(sla):
    if sla=='all':
        delete_redis_keys("*")
        print('all')
    else:
        print(get_last_key_change(sla+'__sla_status'))
        delete_redis_keys("*_"+sla)
        delete_redis_keys(sla+"_packetloss")
        delete_redis_keys(sla+"_MOS")
        delete_redis_keys(sla+"_jitter")
        delete_redis_keys(sla+"_delay")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        function_name = sys.argv[1]
        if function_name == "sla_status_summary":
            print(sla_status_summary())

        elif function_name == "overlay_summary":
            print(overlay_summary())

        elif function_name == "underlay_summary":
            print(underlay_summary())

        elif function_name == "clear":
            if len(sys.argv) > 2:
                sla = sys.argv[2]
                clear(sla)
            else:
                print("No peer specified")
                sys.exit(1)


        elif function_name == "overlay":
            if len(sys.argv) > 2:
                peer = sys.argv[2]
                print(overlay(peer))
            else:
                print("No peer specified")
                sys.exit(1)

        elif function_name == "underlay":
            if len(sys.argv) > 2:
                peer = sys.argv[2]
                print(underlay(peer))
            else:
                print("No peer specified")
                sys.exit(1)
        elif function_name == "sla_status":
            if len(sys.argv) > 2:
                peer = sys.argv[2]
                print(sla_status("vti"+peer))
            else:
                print("No peer specified")
                sys.exit(1)
        else:
            print(f"Unknown function: {function_name}")
            sys.exit(1)
    else:
        print("No function specified")
        sys.exit(1)
