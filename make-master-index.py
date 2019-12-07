#!/usr/bin/env python3

"""
This constructs the Master-Index file (the plain text one, not the XML).
It works by reading the ls-lR listing, extracting all the Index files,
and concatenating them together.

    cd /var/ifarchive/htdocs
    ls -lRn if-archive > if-archive/ls-lR
    /var/ifarchive/bin/make-master-index.py if-archive/ls-lR > if-archive/Master-Index

"""

import sys
import re

rootdir = '/var/ifarchive/htdocs'

dirre = re.compile('^if-archive.*:$')

currentdir = None

lsfile = open(sys.argv[1], encoding='utf-8')

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
            print('# ' + basename)
            filename = (rootdir + '/' + currentdir + '/Index')
            fl = open(filename, 'r', encoding='utf-8')
            for subln in fl.readlines():
                if subln.startswith('#'):
                    subln = '#'+subln
                print(subln, end='')
            fl.close()
            str = None
            print()
            print('------------------------------------------------------')
            
lsfile.close()
