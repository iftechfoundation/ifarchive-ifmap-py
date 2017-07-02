#!/usr/bin/env python3

import sys
import os.path
import optparse

popt = optparse.OptionParser(usage='ifmap.py')

popt.add_option('--index',
                action='store', dest='indexpath',
                help='pathname of Master-Index')
popt.add_option('--src',
                action='store', dest='libdir',
                help='pathname of directory containing template files')
popt.add_option('--tree',
                action='store', dest='treedir',
                help='pathname of directory containing archive files')
popt.add_option('--dest',
                action='store', dest='destdir',
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

class ParamFile:
    def __init__(self, filename):
        self.filename = filename
        self.map = {}
        self.body = ''
        
        fl = open(filename, encoding='utf-8')
        while True:
            ln = fl.readline()
            if not ln:
                break
            ln = ln.strip()
            if not ln:
                break
            key, dummy, val = ln.partition(':')
            if not dummy:
                print('Problem: no colon in header line: %d' % (ln,))
                continue
            self.map[key.strip()] = val.strip()

        self.body = fl.read()
        fl.close()

    def get(self, key, default=None):
        return self.map.get(key, default)

def read_lib_file(filename, default):
    if not filename:
        return default
    fl = open(os.path.join(opts.libdir, filename), encoding='utf-8')
    res = fl.read()
    fl.close()
    return res

# Begin work!

(opts, args) = popt.parse_args()

if not opts.libdir:
    raise Exception('--src argument required')
if not opts.destdir:
    raise Exception('--dest argument required')

plan = ParamFile(os.path.join(opts.libdir, 'index'))

filename = plan.get('Top-Level-Template')
toplevel_body = read_lib_file(filename, 'Welcome to the archive.\n')

filename = plan.get('Dir-List-Template')
dirlist_body = read_lib_file(filename, '<html><body>\n{_dirs}\n</body></html>\n')

filename = plan.get('XML-Template')
xmllist_body = read_lib_file(filename, '<xml>\n{_dirs}\n</xml>\n')

filename = plan.get('Date-List-Template')
datelist_body = read_lib_file(filename, '<html><body>\n{_files}\n</body></html>\n')
