#!/usr/bin/env python3

"""
Silly little script to grovel through ifarch.config for a key.
This winds up being useful in the build-indexes script.

The config file is at $IFARCHIVE_CONFIG, or /var/ifarchive/lib/ifarch.config
if the env var is not set.
"""

import sys
import os, os.path
import configparser

if len(sys.argv) <= 1:
    print('usage: configparse DOMAIN:KEY [ DEFAULT ]')
    sys.exit(1)

keystr = sys.argv[1]
defval = None
if len(sys.argv) >= 3:
    defval = sys.argv[2]

if ':' in keystr:
    domain, _, key = keystr.partition(':')
else:
    key = keystr
    domain = 'DEFAULT'

    
configpath = '/var/ifarchive/lib/ifarch.config'
configpath = os.environ.get('IFARCHIVE_CONFIG', configpath)
if not os.path.isfile(configpath):
    print('Config file not found: ' + configpath)
    sys.exit(1)


config = configparser.ConfigParser()
config.read(configpath)


try:
    map = config[domain]
    result = map[key]
except:
    if defval is None:
        print('Key not found: ' + keystr)
        sys.exit(1)
    result = defval

print(result)
sys.exit(0)
