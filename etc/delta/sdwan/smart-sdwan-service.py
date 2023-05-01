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
import threading
import time
import re
import subprocess
import redis


def get_config():
    """
    Retrive CLI config as dictionary. Dictionary can never be empty
    """
    try:
        conf = Config()
        vti = conf.get_config_dict(['interfaces','vti'])
        sdwan = conf.get_config_dict(['sdwan'])
        vrf_ctrl = conf.get_config_dict(['vrf','name','CTRL'])
        return  vti, sdwan, vrf_ctrl
    except Exception as e:
        print("Error: Could not get required configurations\n", e)

vti, sdwan,vrf_ctrl = get_config()
print(sdwan)
# underlays = sdwan['underlay']

# # Connect to Redis
# r = redis.Redis(host='localhost', port=6379, db=0)

# while True:
#     # Monitor each interface
#     for underlay in underlays:
#         interface=underlays[underlay]['interface']
#         print(interface,"\n####\n" ,underlay)
    #     # Run the bmon command
    #     output = subprocess.check_output(["sudo", "bmon", "-b", "-p", interface, "-o", "ascii", "-r", "10"]).decode()

    #     # Parse the output to extract the RX and TX values
    #     rx_bps = int(output.split()[1])
    #     rx_pps = int(output.split()[3])
    #     tx_bps = int(output.split()[5])
    #     tx_pps = int(output.split()[7])

    #     # Insert the values into Redis
    #     r.lpush(f"load_{interface}", rx_bps, rx_pps, tx_bps, tx_pps)

    # # Wait before checking again
    # time.sleep(10)
