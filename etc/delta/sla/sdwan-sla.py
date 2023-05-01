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


def send_continuous_ping(key, value):
    # Get remote address
    local_address = value["address"][0]
    remote_address = get_remote_address(local_address)

    # Send continuous SLA ICMP messages
    interval = int(value["sla"]["interval"]) / 1000
    timeout = int(value["sla"]["timeout"]) / 1000
    icmp_command = f"ping -W timeout -i {interval} {remote_address} -I {key} -O"
    # icmp_command = f"ping -i {interval} -W {timeout} {remote_address} -I {key}"

    # Run the ping command as a subprocess
    process = subprocess.Popen(icmp_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=True, text=True)

    # Process the output line by line
    for line in iter(process.stdout.readline, ''):
        rtt_search = re.search(r'time=(\d+(\.\d+)?)', line)
        if rtt_search:
            rtt = rtt_search.group(1)
        else:
            rtt = 0
        # print(key, rtt)
        # Save RTT value to Redis with timestamp and TTL of 300 seconds
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        redis_key = f"{timestamp}_{key}"
        r.set(redis_key, rtt, ex=ttl)

# Create threads for each VTI interface
threads = []
for key, value in data.items():
    t = threading.Thread(target=send_continuous_ping, args=(key, value))
    t.start()
    threads.append(t)

# Wait for all threads to finish
for t in threads:
    t.join()