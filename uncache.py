#!/usr/bin/env python3

# uncache.py: Wipe a URL from the CloudFlare cache.

# The argument is anything that looks like a Archive file URL or URI.
# You can specify any number of them. All of the following are equivalent,
# and will purge the file "foo" for all our primary domains (ifarchive.org,
# www.ifarchive.org, and mirror.ifarchive.org):
#
#   foo
#   if-archive/foo
#   /if-archive/foo
#   http://ifarchive.org/if-archive/foo
#   https://ifarchive.org/if-archive/foo
#
# You can also specify a URL directly. It will not be normalized.
#
#   -u http://ifarchive.org/misc/ifarchive.css

import sys
import os, os.path
import re
import optparse
import json
import configparser
import hashlib
import urllib.request
import zipfile

popt = optparse.OptionParser(usage='uncache.py')

popt.add_option('-u', '--url',
                action='append', dest='urls',
                help='purge this URL as-is (do not treat it as a file under if-archive)')

popt.add_option('-n', '--dryrun',
                action='store_true', dest='dryrun',
                help='show the URLs that will be purged, but don\'t call CloudFlare')

popt.add_option('-z', '--zip',
                action='store_true', dest='zip',
                help='for zip files, also purge the Unbox content URLs')

(opts, args) = popt.parse_args()

if not args and not opts.urls:
    print('usage: uncache.py URIs...')
    sys.exit(0)

# Read the configuration values from configpath.

configpath = '/var/ifarchive/lib/cloudflare.config'
confparse = configparser.ConfigParser()
confparse.read(configpath)
config = confparse['DEFAULT']

api_secret_key = config['api_secret_key']
zone_id = config['zone_id']
account_email = config['account_email']
archivedir = config.get('archivedir', '/var/ifarchive/htdocs/if-archive')

MAXFILES = 16

def path_to_hash(path):
    # Convert a path to a hash string. This algorithm follows Unbox; see:
    # https://github.com/iftechfoundation/ifarchive-unbox/blob/main/doc/spec.md
    bytes = hashlib.sha512(path.encode()).hexdigest()[0:12]
    ival = int(bytes, 16)
    alpha = '0123456789abcdefghijklmnopqrstuvwxyz'
    res = []
    while ival:
        ch = alpha[ival % 36]
        ival = ival // 36
        res.insert(0, ch)
    while len(res) < 10:
        res.insert(0, '0')
    return ''.join(res)

# Extract the URLs from the command-line arguments.
urls = []

# Raw URLs are used directly.
if opts.urls:
    urls.extend(opts.urls)

# Figure out the URLs for file arguments, and normalize them.

pat = re.compile('^http[s]?://[a-z.]*ifarchive[.]org/', re.IGNORECASE)

prefixes = [
    'http://ifarchive.org/if-archive/',
    'https://ifarchive.org/if-archive/',
    'http://www.ifarchive.org/if-archive/',
    'https://www.ifarchive.org/if-archive/',
    'http://mirror.ifarchive.org/if-archive/',
    'https://mirror.ifarchive.org/if-archive/',
    # Don't need the http: version for unbox; it redirects. But the query param *does* need all versions.
    'https://unbox.ifarchive.org/?url=/if-archive/',
    'https://unbox.ifarchive.org/?url=http://ifarchive.org/if-archive/',
    'https://unbox.ifarchive.org/?url=https://ifarchive.org/if-archive/',
]

filenames = []

for val in args:
    match = pat.match(val)
    if match:
        val = val[ match.end() : ]
    if val.startswith('/'):
        val = val[ 1 : ]
    if val.startswith('if-archive/'):
        val = val[ 11 : ]
    filenames.append(val)

for val in filenames:
    for prefix in prefixes:
        urls.append(prefix+val)

if opts.zip:
    for val in filenames:
        path = os.path.join(archivedir, val)
        hash = path_to_hash(val)
        if not os.path.isfile(path):
            print('zip file not found:', path)
            continue
        try:
            with zipfile.ZipFile(path) as zipfl:
                for val in zipfl.namelist():
                    urls.append('https://unbox.ifarchive.org/%s/%s' % (hash, val,))
        except Exception as ex:
            print('%s: %s' % (path, ex,))

# Got all the URLs.
print('Purging %d urls:' % (len(urls),))
for val in urls:
    print(val)

if opts.dryrun:
    sys.exit()

cmd = 'purge_cache'
requrl = 'https://api.cloudflare.com/client/v4/zones/%s/%s' % (zone_id, cmd)
headers = {
    'Content-Type': 'application/json',
    'X-Auth-Key': api_secret_key,
    'X-Auth-Email': account_email,
}

# Transmit the API request(s).

try:
    urlsleft = list(urls)
    while urlsleft:
        sendurls, urlsleft = urlsleft[ : MAXFILES ], urlsleft[ MAXFILES : ]

        data = json.dumps({ 'files':sendurls }).encode()
        req = urllib.request.Request(requrl, method='POST', data=data, headers=headers)
    
        with urllib.request.urlopen(req) as res:
            dat = res.read()
            dat = json.loads(dat.decode())
            print(res.getcode(), 'success:', dat.get('success'))
    
except urllib.error.HTTPError as ex:
    dat = ex.fp.read()
    msg = dat.decode()
    print('%s: %s' % (ex, msg,))
except Exception as ex:
    print('%s' % (ex,))

