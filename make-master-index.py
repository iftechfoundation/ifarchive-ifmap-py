#!/usr/bin/env python3

"""
This constructs the Master-Index file (the plain text one, not the XML).
It works by reading the ls-lR listing, extracting all the Index files,
and concatenating them together.

Usage: make-master-index.py ls-lR [ htdocs ]

The second argument is optional, and defaults to /var/ifarchive/htdocs.

In normal Archive operation:

    cd /var/ifarchive/htdocs
    ls -lRn if-archive > if-archive/ls-lR
    /var/ifarchive/bin/make-master-index.py if-archive/ls-lR > if-archive/Master-Index

"""

import sys
import re

lspath = sys.argv[1]
rootdir = '/var/ifarchive/htdocs'
if len(sys.argv) >= 2:
    rootdir = sys.argv[2]

dirre = re.compile('^if-archive.*:$')

currentdir = None

lsfile = open(lspath, encoding='utf-8')

for line in lsfile.readlines():
    res = dirre.match(line)
    if (res != None):
        line = line.strip()
        line = line[ : -1]
        currentdir = line
    else:
        line = line.strip()
        if (line[-6 : ] == ' Index' and currentdir != None):
            basename = (currentdir + ':')
            print()
            print(basename)
            print('-' * len(basename))
            filename = (rootdir + '/' + currentdir + '/Index')
            fl = open(filename, 'r')
            str = fl.read()
            fl.close()
            print(str, end='')
            str = None
            
lsfile.close()
