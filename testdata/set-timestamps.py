#!/usr/bin/env python3

# This sets the timestamps of all the files under testdata/if-archive.
# This lets us run ifmap.py on the test data with predictable results.

import sys, os
import time

common_timestamp = 1540000000  # 20 Oct 2018

timestamps = {
    'file-1.txt': 1539500000,
    'file-2.txt': 1539600000,
    'file-3.txt': 1539700000,
    'all.zip':    1539700000,
    'game1-v1':   1539000000,
    'game1-pre':  1538800000,
}

for root, dirs, files in os.walk('testdata/if-archive'):
    for file in files:
        val = timestamps.get(file, common_timestamp)
        path = os.path.join(root, file)
        if os.path.islink(path):
            continue
        os.utime(path, times=(val, val))
        timestr = time.strftime('%H:%M:%S %d-%b-%Y', time.gmtime(val))
        #print('%s: %s' % (path, timestr))
        
