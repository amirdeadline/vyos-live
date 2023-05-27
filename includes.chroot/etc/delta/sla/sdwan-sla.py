import json
import time
import redis
import subprocess
from datetime import datetime
from ipaddress import ip_interface
import threading
import re
ttl=300
# Load JSON data from file
json_file = '/tmp/sla.conf'
with open(json_file, 'r') as f:
    data = json.load(f)

# Connect to Redis server
r = redis.Redis(host='localhost', port=6379, db=0)

def get_remote_address(local_address):
    ip_obj = local_address.split("/")[0]
    
    if int(ip_obj[-1]) % 2 == 0:
        remote_ip= ip_obj[:-1]+str(int(ip_obj[-1])+1)
    else:
        remote_ip= ip_obj[:-1]+str(int(ip_obj[-1])-1)
    return str(remote_ip)

def send_continuous_ping(key, value, underlay=False):
    # Get remote address
    if underlay:
        # If this is an underlay interface, ping known addresses
        targets = ["google.com"]
        source_interface = value['interface']
    elif "address" not in value:
        print(f"Skipping interface {key} as it has no IP address configured")
        return
    else:
        local_address = value["address"][0]
        targets = [get_remote_address(local_address)]
        source_interface = key

    # Send continuous SLA ICMP messages
    interval = int(value["sla"]["interval"]) / 1000
    timeout = int(value["sla"]["timeout"]) / 1000

    # Run the ping command as a subprocess for each target
    for remote_address in targets:
        icmp_command = f"ping -W {timeout} -i {interval} {remote_address} -I {source_interface} -O"
        process = subprocess.Popen(icmp_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=True, text=True)

        # Process the output line by line
        for line in iter(process.stdout.readline, ''):
            rtt_search = re.search(r'time=(\d+(\.\d+)?)', line)
            if rtt_search:
                rtt = rtt_search.group(1)
            else:
                rtt = 0

            # Save RTT value to Redis with timestamp and TTL of 300 seconds
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            redis_key = f"{timestamp}_{key}"
            r.set(redis_key, rtt, ex=ttl)

# Create threads for each interface
threads = []
for key, value in data.items():
    try:
        if key.startswith('vti'):
            t = threading.Thread(target=send_continuous_ping, args=(key, value))
        else:
            # If the key does not start with 'vti', assume it's an underlay interface
            t = threading.Thread(target=send_continuous_ping, args=(key, value, True))
        t.start()
        threads.append(t)
    except:
        print(f"SLA Config is not comlelete fr interface/Underlay {key}")


# Wait for all threads to finish
for t in threads:
    t.join()