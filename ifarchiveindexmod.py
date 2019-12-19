import os
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

    def rewrite(self, olddir=None, dryrun=False):
        for (dirname, dir) in self.dirs.items():
            if dir.isdirty():
                print('Rewriting %s' % (dir.dirname,))
                dir.rewrite(olddir, dryrun=dryrun)

# A filename header starts with exactly one "#" (an h1 header in Markdown)
filename_pattern = re.compile('^#[^#]')

# These patterns match the rules of metadata lines as defined in the
# Markdown extension:
# https://python-markdown.github.io/extensions/meta_data/
meta_start_pattern = re.compile('^[ ]?[ ]?[ ]?([a-zA-Z0-9_-]+):')
meta_cont_pattern = re.compile('^(    |\\t)')

class IndexDir:
    def __init__(self, dirname, rootdir=None):
        self.dirname = dirname
        self.indexpath = os.path.join(rootdir, dirname, 'Index')

        self.description = []
        self.files = OrderedDict()
        
        infl = open(self.indexpath, encoding='utf-8')
        curfile = None
        curmetaline = None
        
        for ln in infl.readlines():
            if filename_pattern.match(ln):
                # File entry header.
                filename = ln[1:].strip()
                curfile = IndexFile(filename, self)
                curmetaline = True
                self.files[filename] = curfile
                continue
            
            if not curfile:
                # Directory description line.
                self.description.append(ln)
                continue

            # Part of the file entry.
            if curmetaline is not None:
                match = meta_start_pattern.match(ln)
                match2 = meta_cont_pattern.match(ln)
                if ln.strip() == '':
                    curmetaline = None
                elif match:
                    # New metadata line
                    curmetaline = match.group(1)
                    val = ln[match.end() : ].strip()
                    curfile.add_metadata(curmetaline, val, dirty=False)
                    continue
                elif type(curmetaline) is str and match2:
                    val = ln[match2.end() : ].strip()
                    curfile.add_metadata(curmetaline, val, dirty=False)
                    continue
                else:
                    curmetaline = None
                # We're done with the metadata, so this is a description line.

            # For consistency, the description will always start with a blank line.
            if len(curfile.description) == 0 and ln.strip() != '':
                curfile.description.append('\n')
                
            curfile.description.append(ln)
            
                
        infl.close()

    def __repr__(self):
        return '<IndexDir %s>' % (self.dirname,)

    def isdirty(self):
        for file in self.files.values():
            if file.dirty:
                return True
        return False

    def getfile(self, filename):
        if filename in self.files:
            return self.files[filename]

        # Create a new IndexFile entry.
        curfile = IndexFile(filename, self)
        self.files[filename] = curfile
        curfile.description.append('\n')
        curfile.dirty = True
        return curfile

    def rewrite(self, olddir=None, dryrun=False):
        newpath = self.indexpath+'-new'
        outfl = open(newpath, 'w', encoding='utf-8')
        for ln in self.description:
            outfl.write(ln)

        for (filename, file) in self.files.items():
            outfl.write('# %s\n' % (file.filename,))
            for (key, ls) in file.metadata.items():
                first = True
                for val in ls:
                    if first:
                        outfl.write('%s: %s\n' % (key, val,))
                        first = False
                    else:
                        outfl.write('    %s\n' % (val,))
            for ln in file.description:
                outfl.write(ln)
            if not dryrun:
                file.dirty = False

        outfl.close()

        if dryrun:
            return

        if olddir:
            val = self.dirname.replace('/', 'X') + 'XIndex'
            oldpath = os.path.join(olddir, val)
            os.replace(self.indexpath, oldpath)

        os.replace(newpath, self.indexpath)

class IndexFile:
    def __init__(self, filename, dir):
        self.filename = filename
        self.dir = dir
        self.description = []
        self.metadata = OrderedDict()
        self.dirty = False
        
    def __repr__(self):
        return '<IndexFile %s>' % (self.filename,)

    def add_metadata(self, key, val, dirty=True):
        ls = self.metadata.get(key)
        if ls is None:
            ls = []
            self.metadata[key] = ls
        ls.append(val)
        if dirty:
            self.dirty = True
