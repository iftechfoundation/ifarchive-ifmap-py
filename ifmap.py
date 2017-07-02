#!/usr/bin/env python3

import optparse

popt = optparse.OptionParser(usage='ifmap.py')

popt.add_option('--index',
                action='store', dest='indexpath',
                help='pathname of Master-Index')
popt.add_option('--src',
                action='store', dest='libpath',
                help='pathname of directory containing template files')
popt.add_option('--dest',
                action='store', dest='destpath',
                help='pathname of directory to write index files')

popt.add_option('--xml',
                action='store_true', dest='buildxml',
                help='also create a Master-Index.xml file in the dest directory')
popt.add_option('--exclude',
                action='store_true', dest='excludemissing',
                help='files without index entries are excluded from index listings')
popt.add_option('-v', '--verbose',
                action='store_true', dest='verbose',
                help='print verbose output')

(opts, args) = popt.parse_args()
