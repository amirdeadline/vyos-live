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
