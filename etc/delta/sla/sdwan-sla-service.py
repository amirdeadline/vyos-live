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

# Configure logging
log_file = '/var/log/delta/sla.log'
logging.basicConfig(filename=log_file, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_script(script_name):
    subprocess.run(["python3", script_name])

sdwan_sla_script = "/etc/delta/sla/sdwan-sla.py"
sla_thread = threading.Thread(target=run_script, args=(sdwan_sla_script,))
sla_thread.start()

json_file = '/tmp/sla.conf'
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
while True:
    for vti_interface, config in data.items():
        try:

            # print(vti_interface)
            rtts, ttls = get_vti_data(vti_interface)
            # Perform calculations for packet loss, jitter, delay, and MOS score
            n = int(config["sla"]["threshold"])
            packetloss_default = 20
            
            if "packetloss" in config["sla"]:
                packetloss_default = float(config["sla"]["packetloss"])
            # Check if the SLA conditions are met and update the SLA status
            
            try:
                old_sla_status = int((r.get(f'{vti_interface}_sla_status')).decode('utf-8'))
            except:
                old_sla_status=1
            cost_value= int(ospf['ospf']['interface'][vti_interface]['cost'])
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
                if sla==0:
                    sla_status="DOWN"
                    new_cost = cost_value + 1000
                    # Set the new OSPF cost
                    subprocess.run(
                        ["vtysh", "-c", f"conf t", "-c", f"interface {vti_interface}", "-c", f"ip ospf cost {new_cost}"]
                    )
                    print(f"SLA is down Tried to change Cost on vti {vti_interface}")
                    # changed_interfaces.append(vti_interface)

                else:
                    sla_status="UP"
                    # Reset OSPF cost to the original value
                    subprocess.run(
                        ["vtysh", "-c", f"conf t", "-c", f"interface {vti_interface}", "-c", f"ip ospf cost {cost_value}"]
                    )
                    # changed_interfaces.remove(vti_interface)
                reset_conntrack(vti_interface)
                logging.critical(f"SLA status for {vti_interface} changed from {old_sla_status} to {sla_status}")
            logging.info(f"SLA Stistics for {vti_interface} is SLA STATUS={sla}, Packet_loss:{packetloss}, Jitter:{jitter}, delay:{delay}, MOS Score:{mos}")
            update_redis_metrics(vti_interface, sla, packetloss, jitter, delay, mos)
            print(vti_interface, sla, packetloss, jitter, delay, mos)
        except Exception as e:
            logging.error(f"Error processing SLA status for {vti_interface}: {e}")
            print(f"Error happened : {e}")
    time.sleep(10)
