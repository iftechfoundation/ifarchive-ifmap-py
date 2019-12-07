#!/var/ifarchive/bin/python

"""
This constructs the Master-Index file (the plain text one, not the XML).
It works by reading the ls-lR listing, extracting all the Index files,
and concatenating them together.

    cd /var/ifarchive/htdocs
    ls -lRn if-archive > if-archive/ls-lR
    /var/ifarchive/bin/make-master-index.py < if-archive/ls-lR > if-archive/Master-Index

"""

import sys
import string
import fileinput
import re

rootdir = '/var/ifarchive/htdocs'

dirre = re.compile('^if-archive.*:$')

currentdir = None

for line in fileinput.input('-'):
    res = dirre.match(line)
    if (res != None):
        line = string.strip(line)
        line = line[ : -1]
        currentdir = line
    else:
        line = string.strip(line)
        if (line[-6 : ] == ' Index' and currentdir != None):
            basename = (currentdir + ':')
            print
            print basename
            print ('-' * len(basename))
            filename = (rootdir + '/' + currentdir + '/Index')
            fl = open(filename, 'r')
            str = fl.read()
            fl.close()
            print str,
            str = None
            
