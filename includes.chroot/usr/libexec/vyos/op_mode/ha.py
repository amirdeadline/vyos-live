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

master_config = "/etc/delta/ha/sla.conf"
slave_config = "/etc/delta/ha/sla.conf"
