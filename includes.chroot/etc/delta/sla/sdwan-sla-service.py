import json
from vyos.config import Config
import redis
import logging
from collections import defaultdict
from datetime import datetime, timedelta
import time
import threading
import time
import re
import subprocess
import os
# Configure logging
log_file = '/var/log/delta/sla.log'
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_script(script_name):
    subprocess.run(["python3", script_name])

sdwan_sla_script = "/etc/delta/sla/sdwan-sla.py"
sla_thread = threading.Thread(target=run_script, args=(sdwan_sla_script,))
sla_thread.start()

json_file = '/tmp/sla.conf'
if not os.path.exists(json_file):
    with open(json_file, "w") as f:
        json.dump({}, f)
with open(json_file, 'r') as f:
    try:
        data = json.load(f)
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing JSON config file: {e}")
        raise

r = redis.Redis(host='localhost', port=6379, db=0)

def get_ospf_config():
    """
    Retrive CLI config as dictionary.
    """
    try:
        conf = Config()
        base = ['vrf','name','CTRL','protocols','ospf']
        ospf = conf.get_config_dict(base)
        return ospf
    except Exception as e:
        print("Error: Could not get OSPF configurations\n", e)

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

def get_bgp_config(underlay):
    """
    Retrive CLI config as dictionary.
    """
    try:
        conf = Config()
        base = ['vrf','name',underlay,'protocols','bgp']
        bgp = conf.get_config_dict(base)
        return bgp
    except Exception as e:
        print("Error: Could not get BGP configurations\n", e)

def get_bgp_neighbor(underlay):
    """
    Retrieve the neighbor IP address from the BGP configuration.

    :param underlay: underlay interface name
    :return: BGP neighbor IP address
    """
    bgp = get_bgp_config(underlay)
    neighbor = next(iter(bgp['bgp']['neighbor']), None)
    return neighbor

def update_bgp_default_originate(underlay, neighbor, route_map):
    """
    Update the route map for the default-originate command in the BGP configuration for a specific neighbor.

    :param underlay: underlay interface name
    :param neighbor: BGP neighbor IP address
    :param route_map: new route map name
    """
    subprocess.run(
        ["vtysh", "-c", f"conf t", "-c", f"router bgp 65533 vrf {underlay}", "-c", f"address-family ipv4 unicast", "-c", f"neighbor {neighbor} default-originate route-map {route_map}"]
    )
    
def calculate_average(lst):
    """
    Calculate the average of the values in the list.

    :param lst: list of values
    :return: average of the values in the list
    """
    return sum(lst) / len(lst) if lst else 0

def calculate_packetloss(lst):
    return 100 * lst.count(0) / len(lst) if lst else 0

def calculate_jitter(lst):
    if not lst or len(lst) < 2:
        return 0
    diffs = [abs(lst[i] - lst[i - 1]) for i in range(1, len(lst))]
    return calculate_average(diffs)

def calculate_mos(rtt, packetloss, jitter):
    r_factor = 93.2 - (rtt / 40) - (14 * packetloss) - (2 * jitter)
    if r_factor < 0:
        r_factor = 0
    if r_factor > 100:
        r_factor = 100

    if r_factor < 60:
        mos = 1 + 0.035 * r_factor + 7 * (0.000001) * (r_factor) * (100 - r_factor)
    else:
        mos = 4.5
    return mos

def get_vti_data(interface_name):
    keys = r.keys(f'*_{interface_name}')
    keys.sort(reverse=True)
    rtts = []
    ttls = []

    for key in keys:
        try:
            rtt = float(r.get(key))
            ttl = r.ttl(key)
            rtts.append(rtt)
            ttls.append(ttl)
        except:
            pass

    return rtts, ttls

def reset_conntrack(interface_name):
    """
    Reset conntrack sessions for the specified VTI interface.

    :param interface_name: VTI interface name
    """
    subprocess.run(["conntrack", "-D", "-i", interface_name])

def update_last_change(interface_name):
    """
    Update Redis with the current datetime as the last change time for a specific interface.

    :param interface_name: Interface name
    """
    last_change_key = f'{interface_name}_last_change'
    current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    r.set(last_change_key, current_datetime)

def update_redis_metrics(interface_name, sla_status, packetloss, jitter, delay, mos):
    """
    Update Redis with the calculated metrics and SLA status.

    :param interface_name: VTI interface name
    :param sla_status: SLA status ("UP" or "DOWN")
    :param packetloss: average packet loss
    :param jitter: average jitter
    :param delay: average delay
    :param mos: average MOS score
    """
    r.set(f'{interface_name}_sla_status', sla_status)
    r.set(f'{interface_name}_packetloss', packetloss)
    r.set(f'{interface_name}_jitter', jitter)
    r.set(f'{interface_name}_delay', delay)
    r.set(f'{interface_name}_MOS', mos)
    # print(sla_status)
ospf =get_ospf_config()
changed_interfaces=[]
# Iterate through VTI interfaces and their configurations
first=True
while True:
    for i, config in data.items():
        if first:
            update_last_change(i)
            
        if i[:3].lower()=="vti":
            try:

                # print(i)
                rtts, ttls = get_vti_data(i)
                # Perform calculations for packet loss, jitter, delay, and MOS score
                n = int(config["sla"]["threshold"])
                packetloss_default = 20
                
                if "packetloss" in config["sla"]:
                    packetloss_default = float(config["sla"]["packetloss"])
                # Check if the SLA conditions are met and update the SLA status
                
                try:
                    old_sla_status = int((r.get(f'{i}_sla_status')).decode('utf-8'))
                except:
                    old_sla_status=1
                cost_value= int(ospf['ospf']['interface'][i]['cost'])
                sla = 1
                if all(rtt == 0 for rtt in rtts[:n]):
                    sla = 0
                # print(cost_value, sla, old_sla_status)
                # print(sla)
                jitter = calculate_jitter(rtts)
                packetloss = calculate_packetloss(rtts)
                delay = calculate_average(rtts)
                mos = calculate_mos(delay, packetloss, jitter)
                if "delay" in config["sla"] and delay > float(config["sla"]["delay"]):
                    sla = 0
                if "jitter" in config["sla"] and jitter > float(config["sla"]["jitter"]):
                    sla = 0
                if "mos" in config["sla"] and mos < float(config["sla"]["mos"]):
                    sla = 0
                if packetloss > packetloss_default:
                    sla = 0
                if old_sla_status != sla:
                    update_last_change(i)

                    if sla==0:
                        sla_status="DOWN"
                        new_cost = cost_value + 1000
                        # Set the new OSPF cost
                        subprocess.run(
                            ["vtysh", "-c", f"conf t", "-c", f"interface {i}", "-c", f"ip ospf cost {new_cost}"]
                        )
                        print(f"SLA is down Tried to change Cost on vti {i}")
                        # changed_interfaces.append(i)
                    else:
                        sla_status="UP"
                        # Reset OSPF cost to the original value
                        subprocess.run(
                            ["vtysh", "-c", f"conf t", "-c", f"interface {i}", "-c", f"ip ospf cost {cost_value}"]
                        )
                        # changed_interfaces.remove(i)
                    # reset_conntrack(i)
                    logging.critical(f"SLA status for {i} changed from {old_sla_status} to {sla_status}")
                logging.info(f"SLA Stistics for {i} is SLA STATUS={sla}, Packet_loss:{packetloss}, Jitter:{jitter}, delay:{delay}, MOS Score:{mos}")
                update_redis_metrics(i, sla, packetloss, jitter, delay, mos)
                print(i, sla, packetloss, jitter, delay, mos)
            except Exception as e:
                logging.error(f"Error processing SLA status for {i}: {e}")
                print(f"Error happened : {e}")
        else:
            try:
                sdwan = get_sdwan_config()
                if sdwan['underlay'][i]['transport-id']=='0':
                    print(i)
                    rtts, ttls = get_vti_data(i)
                    # Perform calculations for packet loss, jitter, delay, and MOS score
                    n = int(config["sla"]["threshold"])
                    packetloss_default = 20
                    
                    if "packetloss" in config["sla"]:
                        packetloss_default = float(config["sla"]["packetloss"])
                    # Check if the SLA conditions are met and update the SLA status
                    
                    try:
                        old_sla_status = int((r.get(f'{i}_sla_status')).decode('utf-8'))
                    except:
                        old_sla_status=1
                    sla = 1
                    if all(rtt == 0 for rtt in rtts[:n]):
                        sla = 0
                    # print(cost_value, sla, old_sla_status)
                    # print(sla)
                    jitter = calculate_jitter(rtts)
                    packetloss = calculate_packetloss(rtts)
                    delay = calculate_average(rtts)
                    mos = calculate_mos(delay, packetloss, jitter)
                    if "delay" in config["sla"] and delay > float(config["sla"]["delay"]):
                        sla = 0
                    if "jitter" in config["sla"] and jitter > float(config["sla"]["jitter"]):
                        sla = 0
                    if "mos" in config["sla"] and mos < float(config["sla"]["mos"]):
                        sla = 0
                    if packetloss > packetloss_default:
                        sla = 0
                    if old_sla_status != sla:
                        neighbor= get_bgp_neighbor(i)
                        if sla==0:
                            sla_status="DOWN"
                            # Set the new OSPF cost
                            update_bgp_default_originate(underlay, neighbor, "DEFAULT_ROUTE_PREPEND")
                            print(f"SLA is down Tried to change Cost on vti {i}")
                            # changed_interfaces.append(i)

                        else:
                            sla_status="UP"
                            # Reset OSPF cost to the original value
                            update_bgp_default_originate(underlay, neighbor, "DEFAULT_ROUTE")
                            # changed_interfaces.remove(i)
                        # reset_conntrack(i)
                        logging.critical(f"SLA status for {i} changed from {old_sla_status} to {sla_status}")
                        update_last_change(i)

                    logging.info(f"SLA Stistics for {i} is SLA STATUS={sla}, Packet_loss:{packetloss}, Jitter:{jitter}, delay:{delay}, MOS Score:{mos}")
                    update_redis_metrics(i, sla, packetloss, jitter, delay, mos)
                    print(i, sla, packetloss, jitter, delay, mos)
            except Exception as e:
                logging.error(f"Error processing SLA status for {i}: {e}")
                print(f"Error happened : {e}")
    time.sleep(5)
    first=False
