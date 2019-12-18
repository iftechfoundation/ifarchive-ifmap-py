import os.path
import re
from collections import OrderedDict

"""ifarchiveindexmod:

This module lets you programmatically modify the metadata in selected Index
files. It rewrites the files and stores the old versions in /oldindex
as a backup.
"""

class IndexMod:
    def __init__(self, rootdir):
        self.rootdir = rootdir
        self.archivedir = os.path.join(self.rootdir, 'if-archive')
        if not os.path.exists(self.archivedir):
            raise Exception('%s does not contain an if-archive directory' % (self.archivedir,))

        self.dirs = {}
        
    def getdir(self, dirname):
        if dirname in self.dirs:
            dir = self.dirs[dirname]
        else:
            dir = IndexDir(dirname, rootdir=self.rootdir)
            self.dirs[dirname] = dir
        return dir
            
    def getfile(self, pathname):
        if pathname.startswith('/'):
            pathname = pathname[1:]
        if not pathname.startswith('if-archive/'):
            pathname = 'if-archive/' + pathname
        (dirname, sep, filename) = pathname.rpartition('/')
        if not (sep and filename):
            raise Exception('%s does not have a file path' % (pathname,))

        dir = self.getdir(dirname)
        return dir.getfile(filename)

filename_pattern = re.compile('^#[^#]')

class IndexDir:
    def __init__(self, dirname, rootdir=None):
        self.dirname = dirname
        indexpath = os.path.join(rootdir, dirname, 'Index')

        self.description = []
        self.files = OrderedDict()
        
        infl = open(indexpath, encoding='utf-8')
        curfile = None
        
        for ln in infl.readlines():
            if filename_pattern.match(ln):
                filename = ln[1:].strip()
                curfile = IndexFile(filename, self)
                self.files[filename] = curfile
                continue
            if not curfile:
                self.description.append(ln)
            else:
                curfile.description.append(ln)
                
        infl.close()

    def __repr__(self):
        return '<IndexDir %s>' % (self.dirname,)

    def getfile(self, filename):
        if filename in self.files:
            return self.files[filename]
        
        curfile = IndexFile(filename, self)
        self.files[filename] = curfile
        curfile.description.append('\n')
        return curfile

class IndexFile:
    def __init__(self, filename, dir):
        self.filename = filename
        self.dir = dir
        self.description = []
        
    def __repr__(self):
        return '<IndexFile %s>' % (self.filename,)

