#!/usr/bin/env python3

# uncache.py: Wipe a URL from the CloudFlare cache.

import sys
import re
import json
import configparser
import urllib.request

if len(sys.argv) <= 1:
    print('usage: uncache.py URIs...')
    sys.exit(0)

# Read the configuration values from configpath.
# I refuse to formalize Windows INI format, so the config file just
# looks like:
#   api_secret_key = ...
#   zone_id = ...
#   account_email = ...

configpath = '/var/ifarchive/lib/cloudflare.config'
dat = '[DEFAULT]\n' + open(configpath).read()
confparse = configparser.ConfigParser()
confparse.read_string(dat)
config = confparse['DEFAULT']

api_secret_key = config['api_secret_key']
zone_id = config['zone_id']
account_email = config['account_email']

# Extract the URLs from the command-line arguments. We accept anything
# that looks like a URL or URI. All of the following are equivalent
# command-line arguments:
#   foo
#   if-archive/foo
#   /if-archive/foo
#   http://ifarchive.org/if-archive/foo
#   https://ifarchive.org/if-archive/foo

urls = []

pat = re.compile('^http[s]?://[a-z.]*ifarchive[.]org/', re.IGNORECASE)

prefixes = [
    # Don't need the https: versions; Cloudflare treats them the same.
    'http://ifarchive.org/if-archive/',
    'http://www.ifarchive.org/if-archive/',
    'http://mirror.ifarchive.org/if-archive/',
]

for val in sys.argv[1:]:
    match = pat.match(val)
    if match:
        val = val[ match.end() : ]
    if val.startswith('/'):
        val = val[ 1 : ]
    if val.startswith('if-archive/'):
        val = val[ 11 : ]
    for prefix in prefixes:
        urls.append(prefix+val)

print(urls)

cmd = 'purge_cache'
url = 'https://api.cloudflare.com/client/v4/zones/%s/%s' % (zone_id, cmd)
headers = {
    'Content-Type': 'application/json',
    'X-Auth-Key': api_secret_key,
    'X-Auth-Email': account_email,
}
data = json.dumps({ 'files':urls }).encode()

# Transmit the API request.

req = urllib.request.Request(url, method='POST', data=data, headers=headers)

with urllib.request.urlopen(req) as res:
    dat = res.read()
    dat = json.loads(dat.decode())
    print(res.getcode(), 'success:', dat.get('success'))
    

