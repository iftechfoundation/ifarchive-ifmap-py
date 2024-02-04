#!/usr/bin/env python3

"""
This constructs the Master-Index file (the plain text one, not the XML).
It works by walking the directory tree, extracting all the Index files,
and concatenating them together. It adds a # directory header at the top
of each Index file, and increases the # header depth (of files, etc) by
one.

Usage: make-master-index.py [ htdocs ]

The argument is optional, and defaults to /var/ifarchive/htdocs.

(This used to read the ls-lR file, but not any more.)

In normal Archive operation:

    /var/ifarchive/bin/make-master-index.py > if-archive/Master-Index

"""

import sys
import os, os.path
import re

rootdir = '/var/ifarchive/htdocs'
if len(sys.argv) >= 2:
    rootdir = sys.argv[1]

rootarchdir = os.path.join(rootdir, 'if-archive')
    
dirre = re.compile('^if-archive.*:$')

for (dirpath, dirnames, filenames) in os.walk(rootarchdir):
    if 'Index' in filenames:
        currentdir = os.path.relpath(dirpath, start=rootdir)
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
    
    # Ensure that we visit in Unicode sort order (not case-folded).
    dirnames.sort()

