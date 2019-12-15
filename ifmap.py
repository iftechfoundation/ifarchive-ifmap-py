#!/usr/bin/env python3

import sys
import re
import os
import os.path
import time
import hashlib
from collections import ChainMap, OrderedDict
import optparse
import markdown

ROOTNAME = 'if-archive'
DESTDIR = None

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
                action='store', dest='destdir', default='indexes',
                help='directory to write index files (relative to --tree; default "indexes")')
popt.add_option('--meta',
                action='store', dest='metadir', default='metadata',
                help='directory to write metadata files (relative to --tree; default "metadata")')
popt.add_option('--exclude',
                action='store_true', dest='excludemissing',
                help='files without index entries are excluded from index listings')
popt.add_option('-v', '--verbose',
                action='store_true', dest='verbose',
                help='print verbose output')

class TemplateTag:
    """Data element used inside a Template.
    """
    def __init__(self, val, type=None, args=None):
        self.value = val
        self.type = type
        self.args = args
    def __repr__(self):
        return '<TemplateTag %s:%r>' % (self.type, self.value)
        
class Template:
    """Template: A basic template-substitution system.

    You normally don't create Template objects. Instead, call
    Template.substitute(body, map). This will create a Template
    object if needed (caching known ones for speed) and then perform
    the substitution.

    The template language supports these tags:

    {foo}: Substitute the value of map['foo']. This can be a string/
        int/bool value or a function. Functions must be of the form
        func(outfl) and write text to outfile. (Functions should not
        return anything.)
    {foo|filter}: Same as above, but values are processed through a
        function named filter. (There is a global list of filters, set
        up with the addfilter static method.) You can run several
        filters sequentially by writing |f1|f2|f3. Note that function
        substitutions cannot currently be filtered.
    {?foo}if-yes{/}: If map['foo'] exists, substitute the if-yes part.
    {?foo}if-yes{:}if-no{/}: If map['foo'] exists, substitute the if-yes
        part; otherwise the if-no part.

    If-then tags can be nested. {foo} is an error if the foo tag is
    missing or its value is None.

    The {?foo} test treats missing tags and Python-falsy values
    (None/False/0/'') as "no" results, all other values as "yes".
    """

    tag_pattern = re.compile('[{]([^}]*)[}]')

    filters = {}  # known filter functions (by name)
    
    cache = {}   # known Templates (by body string)

    @staticmethod
    def addfilter(name, func):
        Template.filters[name] = func
    
    @staticmethod
    def substitute(body, map, outfl=sys.stdout):
        template = Template.cache.get(body)
        if template is None:
            template = Template(body)
            Template.cache[body] = template
        template.subst(map, outfl)
    
    def __init__(self, body):
        self.ls = []
        pos = 0
        while True:
            match = Template.tag_pattern.search(body, pos=pos)
            if not match:
                if pos < len(body):
                    tag = TemplateTag(body[pos : ])
                    self.ls.append(tag)
                break

            if match.start() > pos:
                tag = TemplateTag(body[pos : match.start()])
                self.ls.append(tag)
                
            val = match.group(1)
            pos = match.end()
            if val == ':':
                tag = TemplateTag(None, 'else')
            elif val == '/':
                tag = TemplateTag(None, 'endif')
            elif val == '{':
                tag = TemplateTag('{')
            elif val.startswith('?'):
                tag = TemplateTag(val[1:], 'if')
            else:
                args = None
                if '|' in val:
                    args = val.split('|')
                    args = [ el.strip() for el in args if el.strip() ]
                    val = args.pop(0)
                tag = TemplateTag(val, 'var', args)
            self.ls.append(tag)
            
        return

    def __repr__(self):
        ls = []
        for tag in self.ls:
            if tag.type is None:
                ls.append(tag.value)
            elif tag.type == 'if':
                ls.append('{?%s}' % (tag.value,))
            elif tag.type == 'else':
                ls.append('{:}')
            elif tag.type == 'endif':
                ls.append('{/}')
            elif tag.type == 'var':
                if tag.args:
                    args = [ tag.value ] + tag.args
                    ls.append('{%s}' % ('|'.join(args),))
                else:
                    ls.append('{%s}' % (tag.value,))
            else:
                ls.append('{???}')
        return '<Template %r>' % (''.join(ls),)

    def subst(self, map, outfl=sys.stdout):
        activelist = [ True ]
        
        for tag in self.ls:
            if tag.type is None:
                if not activelist[-1]:
                    continue
                outfl.write(tag.value)
            elif tag.type == 'if':
                if not activelist[-1]:
                    activelist.append(False)
                else:
                    val = None
                    if map:
                        val = map.get(tag.value)
                    activelist.append(bool(val))
            elif tag.type == 'else':
                if len(activelist) <= 1 or activelist[-2]:
                    activelist[-1] = not activelist[-1]
            elif tag.type == 'endif':
                activelist.pop()
            elif tag.type == 'var':
                if not activelist[-1]:
                    continue
                val = None
                if map:
                    val = map.get(tag.value)
                if val is None:
                    outfl.write('[UNKNOWN]')
                    print('Problem: undefined brace-tag: %s' % (tag.value,))
                elif callable(val):
                    val(outfl)
                    if tag.args:
                        print('Problem: cannot use filters with a callable value')
                elif type(val) in (str, int, float, bool):
                    res = str(val)
                    if tag.args:
                        for filter in tag.args:
                            func = Template.filters.get(filter)
                            if func:
                                res = Template.filters[filter](res)
                            else:
                                print('Problem: undefined filter: %s' % (filter,))
                    outfl.write(res)
                else:
                    outfl.write('[NOT-PRINTABLE]')
                    print('Problem: unprintable brace-tag type: %s=%r' % (tag.value, val))
    
class ParamFile:
    """ParamFile: Store the contents of the lib/index file. This is a bunch
    of key-value pairs, followed by a plain text body.
    """
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

    def put(self, key, val):
        self.map[key] = val

class NoIndexEntry:
    """NoIndexEntry: A list of directories in which it's okay that there's
    no index entries.

    The logic here is a bit twisty. Normally, if we find a file which
    is not mentioned in any Index file, we print a warning. (If the
    --exclude flag is used, we exclude the file from indexing entirely.
    But that flag is not used in production.)

    The no-index-entry file (in libdir) is a list of files and directories
    in which we do *not* do this check (and therefore print no warning,
    and never exclude files). We use this for directories containing a
    large number of boring files (like info/ifdb), and directories whose
    contents change frequently (like unprocessed).
    """
    def __init__(self):
        self.ls = []
        try:
            filename = os.path.join(opts.libdir, 'no-index-entry')
            fl = open(filename, encoding='utf-8')
        except:
            return
        while True:
            ln = fl.readline()
            if not ln:
                break
            ln = ln.strip()
            self.ls.append(ln)
        fl.close()

    def check(self, path):
        """The argument is the pathname of a file which was found in
        the treedir but which was never mentioned in any Index file.
        
        If the path, or any prefix of the path, exists in our list,
        we print nothing and return False. Otherwise, we print a
        warning and return True (to exclude the file from the index)
        or False (to index the file anyway).
        """
        for val in self.ls:
            if path.startswith(val):
                return False
        sys.stderr.write('File without index entry: %s\n' % (path,))
        return opts.excludemissing
    
class FileHasher:
    """FileHasher: A module which can extract hashes of files.

    Since hashing is this script's slowest task, we keep a cache of
    checksums. The cache file has a very simple tab-separated format:
    
       size mtime md5 sha512 filename

    We only use a cache entry if the size and mtime both match. (So if a
    file is updated, we'll recalculate.)

    We only ever append to the cache file. So if a file is updated, we
    wind up with redundant lines in the cache. That's fine; the latest
    line is the one that counts. But it might be a good idea to delete
    the cache file every couple of years to tidy up.
    """
    def __init__(self):
        # Maps filenames to (size, timestamp, md5, sha512)
        self.cache = {}

        # Create the cache file if it doesn't exist.
        self.cachefile = os.path.join(opts.treedir, 'checksum-cache.txt')

        if not os.path.exists(self.cachefile):
            fl = open(self.cachefile, 'w', encoding='utf-8')
            fl.close()
        
        fl = open(self.cachefile, encoding='utf-8')
        pattern = re.compile('^([0-9]+)\s([0-9]+)\s([0-9a-f]+)\s([0-9a-f]+)\s(.*)$')
        while True:
            ln = fl.readline()
            if not ln:
                break
            ln = ln.rstrip()
            match = pattern.match(ln)
            if match:
                size = int(match.group(1))
                timestamp = int(match.group(2))
                md5 = match.group(3)
                sha512 = match.group(4)
                filename = match.group(5)
                self.cache[filename] = (size, timestamp, md5, sha512)
        fl.close()

    def get_hashes(self, filename, size, timestamp):
        if filename in self.cache:
            (cachesize, cachetimestamp, md5, sha512) = self.cache[filename]
            if size == cachesize and timestamp == cachetimestamp:
                return (md5, sha512)
        if opts.verbose:
            print('Computing hashes for %s' % (filename,))
        (md5, sha512) = self.calculate_hashes(filename)
        self.cache[filename] = (size, timestamp, md5, sha512)
        fl = open(self.cachefile, 'a', encoding='utf-8')
        fl.write('%d\t%d\t%s\t%s\t%s\n' % (size, timestamp, md5, sha512, filename))
        fl.close()
        return (md5, sha512)
            
    def calculate_hashes(self, filename):
        accum_md5 = hashlib.md5()
        accum_sha512 = hashlib.sha512()
        fl = open(filename, 'rb')
        while True:
            dat = fl.read(1024)
            if not dat:
                break
            accum_md5.update(dat)
            accum_sha512.update(dat)
        fl.close()
        return (accum_md5.hexdigest(), accum_sha512.hexdigest())

class SafeWriter:
    """SafeWriter: a class which can write a file atomically.

    This implements a simple pattern: you open a temporary file for
    writing, write data to it, close the file, and then move it
    to its final location.
    """

    def __init__(self, tempname, finalname):
        self.tempname = tempname
        self.finalname = finalname
        self.fl = open(tempname, 'w', encoding='utf-8')

    def stream(self):
        return self.fl

    def resolve(self):
        self.fl.close()
        self.fl = None
        os.replace(self.tempname, self.finalname)

def read_lib_file(filename, default=''):
    """Read a simple text file from the lib directory. Return it as a
    string.
    If filename is None, return the default string instead.
    """
    if not filename:
        return default
    fl = open(os.path.join(opts.libdir, filename), encoding='utf-8')
    res = fl.read()
    fl.close()
    return res

def is_string_nonwhite(val):
    """Return (bool) whether val contains anything besides whitespace.
    """
    return bool(val.strip())
    
def relroot_for_dirname(val):
    """For a directory, return the relative URL which returns to the
    root. "if-archive/games" maps to "../../..".
    """
    num = val.count('/')
    return '../..' + num * '/..'

xify_mode = True

def xify_dirname(val):
    """Convert a directory name to an X-string, as used in the index.html
    filenames. The "if-archive/games" directory is mapped to
    "if-archiveXgames", for example.
    We acknowledge that this is ugly and stupid. It's deprecated; we now
    point people to dir/index.html indexes which don't use the X trick.
    """
    return val.replace('/', 'X')

def indexuri_dirname(val):
    """Convert a directory name to the URI for its index file.
    The global xify_mode switch determines whether we use the X trick
    (see above) or not.
    """
    if xify_mode:
        return val.replace('/', 'X') + '.html'
    else:
        return val + '/'

# All ASCII characters except <&>
htmlable_pattern = re.compile("[ -%'-;=?-~]+")
html_entities = {
    # Newlines and tabs are not encoded.
    '\n': '\n', '\t': '\t',
    # The classic three HTML characters that must be escaped.
    '&': '&amp;', '<': '&lt;', '>': '&gt;',
    # We could add more classic accented characters, but not really important.
    # Actually, if we do, we'd have to distinguish HTML escaping from
    # XML escaping. So let's not.
}

def pluralize_s(val):
    if val == 1 or val == '1':
        return ''
    else:
        return 's'

def pluralize_ies(val):
    if val == 1 or val == '1':
        return 'y'
    else:
        return 'ies'

def slash_add_wbr(val):
    return val.replace('/', '/<wbr>')
    
def escape_html_string(val):
    """Apply the basic HTML/XML &-escapes to a string. Also &#x...; escapes
    for Unicode characters.
    """
    res = []
    pos = 0
    while pos < len(val):
        match = htmlable_pattern.match(val, pos=pos)
        if match:
            res.append(match.group())
            pos = match.end()
        else:
            ch = val[pos]
            ent = html_entities.get(ch)
            if ent:
                res.append(ent)
            else:
                res.append('&#x%X;' % (ord(ch),))
            pos += 1
    return ''.join(res)

urlable_pattern = re.compile('[+-;@-z]+')

def escape_url_string(val):
    """Apply URL escaping (percent escapes) to a string.
    This is a bit over-zealous; it matches the behavior of the original
    C ifmap.
    Does not work correctly on Unicode characters outside the Latin-1
    range (0 to 0xFF).
    """
    res = []
    pos = 0
    while pos < len(val):
        match = urlable_pattern.match(val, pos=pos)
        if match:
            res.append(match.group())
            pos = match.end()
        else:
            ch = val[pos]
            res.append('%%%02X' % (ord(ch) & 0xFF),)
            pos += 1
    return ''.join(res)

def findfile(path):
    """Locate the File object for a given pathname.
    This is a debugging function; call it after the global dirmap
    has been created.
    """
    (dirname, filename) = os.path.split(path)
    if not dirname.startswith('if-archive'):
        if not dirname:
            dirname = 'if-archive'
        else:
            dirname = os.path.join('if-archive', dirname)

    dir = dirmap[dirname]
    return dir.files[filename]

class Directory:
    """Directory: one directory in the big directory map.
    """
    def __init__(self, dirname, dirmap):
        self.dir = dirname
        # Place into the big directory map.
        dirmap[dirname] = self

        self.submap = {}

        self.putkey('dir', dirname)

        pos = dirname.rfind('/')
        if pos < 0:
            self.parentdirname = None
        else:
            parentdirname = dirname[0:pos]
            self.parentdirname = parentdirname
            self.putkey('parentdir', parentdirname)

        # To be filled in later
        self.files = {}
        self.subdirs = {}
        self.parentdir = None

    def __repr__(self):
        return '<Directory %s>' % (self.dir,)

    def getkey(self, key, default=None):
        return self.submap.get(key)
    
    def putkey(self, key, val):
        self.submap[key] = val

metadata_pattern = re.compile('^[ ]*[a-zA-Z0-9_-]+:')

class File:
    """File: one file in the big directory map.
    (There is no global file list. You have to look at dir.files for each
    directory in dirmap.)
    """
    def __init__(self, filename, parentdir):
        self.submap = {}
        self.parentdir = parentdir
        # Place into the parent directory.
        parentdir.files[filename] = self

        self.name = filename
        self.path = parentdir.dir+'/'+filename
        self.metadata = OrderedDict()

        self.putkey('name', filename)
        self.putkey('dir', parentdir.dir)
        self.putkey('path', self.path)

    def __repr__(self):
        return '<File %s>' % (self.name,)

    def complete(self, desclines):
        # Take the accumulated description text and stick it into our
        # File object.
        if desclines:
            val = '\n'.join(desclines)
            filestr = convertermeta.convert(val)
            for (mkey, mls) in convertermeta.Meta.items():
                self.metadata[mkey] = ', '.join(mls)
            convertermeta.Meta.clear()
            ### sort metadata?
            
            self.putkey('desc', filestr)
            self.putkey('hasdesc', is_string_nonwhite(filestr))

            # Remove metadata lines before generating XML.
            pos = 0
            for ln in desclines:
                if not ln.strip():
                    break
                if not (metadata_pattern.match(ln) or ln.startswith('    ')):
                    break
                pos += 1
            val = '\n'.join(desclines[pos:])
            descstr = val.rstrip() + '\n'
            descstr = escape_html_string(descstr)
            self.putkey('xmldesc', descstr)
            self.putkey('hasxmldesc', is_string_nonwhite(descstr))
        
    def getkey(self, key, default=None):
        return self.submap.get(key)
    
    def putkey(self, key, val):
        self.submap[key] = val

def parse_master_index(indexpath, treedir):
    """Parse the Master-Index file, and then go through the directory
    tree to find more files. Return all the known directories as a dict.

    Either or both arguments may be None. At a bare minimum, this always
    returns the root directory.
    """

    dirmap = {}

    dir = Directory(ROOTNAME, dirmap=dirmap)

    if indexpath:
        dirname_pattern = re.compile('^#[ ]*(%s.*):$' % (re.escape(ROOTNAME),))
        filename_pattern = re.compile('^##[^#]')
        dashline_pattern = re.compile('^[ ]*[-+=#*]+[ -+=#*]*$')
        
        dir = None
        file = None
        filedesclines = None
        inheader = True
        headerlines = None
        
        infl = open(indexpath, encoding='utf-8')

        done = False
        while not done:
            ln = infl.readline()
            if not ln:
                done = True
                ln = None
                match = None
            else:
                ln = ln.rstrip()
                match = dirname_pattern.match(ln)

            if done or match:
                # End of a directory block or end of file.
                # Finish constructing the dir entry.

                if dir:
                    if file:
                        # Also have to finish constructing the file entry.
                        file.complete(filedesclines)
                        file = None

                    dirname = dir.dir
                    if opts.verbose:
                        print('Finishing %s...' % (dirname,))

                    while len(headerlines) and headerlines[0] == '':
                        headerlines.pop(0)
                    headerstr = '\n'.join(headerlines)
                    headerstr = headerstr.rstrip() + '\n'
                    # Now headerstr starts with zero newlines and ends
                    # with one newline.
                    anyheader = bool(headerstr.strip())
                    dir.putkey('hasdesc', anyheader)
                    dir.putkey('hasxmldesc', anyheader)
                    if anyheader:
                        # Convert Markdown to HTML.
                        val = converter.convert(headerstr)
                        dir.putkey('header', val)
                        # For XML, we just escape.
                        val = escape_html_string(headerstr)
                        dir.putkey('xmlheader', val)
                    dir = None

                if not done:
                    # Beginning of a directory block.
                    assert(match is not None)
                    dirname = match.group(1)
                    if opts.verbose:
                        print('Starting  %s...' % (dirname,))
                    dir = Directory(dirname, dirmap=dirmap)
                    
                    filedesclines = None
                    inheader = True
                    headerlines = []

                continue

            # We can't do any work outside of a directory block.
            if dir is None:
                continue

            # Skip any line which is entirely dashes (or dash-like
            # characters). But we don't skip blank lines this way.
            if dashline_pattern.match(ln):
                continue

            bx = ln

            if inheader:
                if not filename_pattern.match(bx):
                    # Further header lines become part of headerlines.
                    headerlines.append(bx)
                    continue

                # The header ends when we find a line starting with "##".
                inheader = False

            if filename_pattern.match(bx):
                # Start of a new file block.

                if file:
                    # Finish constructing the file in progress.
                    file.complete(filedesclines)
                    file = None

                # Set up the new file, including a fresh filedesclines
                # accumulator.

                filename = bx[2:].strip()
                bx = ''
                filedesclines = []
                    
                file = File(filename, dir)

            else:
                # Continuing a file block.
                filedesclines.append(bx)

        # Finished reading Master-Index.
        infl.close()

    if treedir:
        # Do an actual scan of the tree and write in any directories
        # we missed. We also take the opportunity to scan file dates
        # and sizes.

        def scan_directory(dirname, parentlist=None, parentdir=None):
            """Internal recursive function.
            """
            if opts.verbose:
                print('Scanning %s...' % (dirname,))
            dir = dirmap.get(dirname)
            if dir is None:
                print('Problem: unable to find directory: %s' % (dirname,))
                return
            
            pathname = os.path.join(treedir, dirname)
            for ent in os.scandir(pathname):
                if ent.name.startswith('.'):
                    continue
                sta = ent.stat(follow_symlinks=False)
                dirname2 = os.path.join(dirname, ent.name)
                pathname = os.path.join(treedir, dirname, ent.name)
                
                if ent.is_symlink():
                    linkname = os.readlink(ent.path)
                    # Symlink destinations should always be relative.
                    if linkname.endswith('/'):
                        linkname = linkname[0:-1]
                    sta2 = ent.stat(follow_symlinks=True)
                    if ent.is_file(follow_symlinks=True):
                        file = dir.files.get(ent.name)
                        if file is None:
                            if noindexlist.check(dirname2):
                                continue
                            file = File(ent.name, dir)
                        file.putkey('islink', True)
                        file.putkey('islinkfile', True)
                        file.putkey('linkpath', linkname) ### canonicalize?
                        file.putkey('date', str(int(sta2.st_mtime)))
                        tmdat = time.gmtime(sta2.st_mtime)
                        file.putkey('datestr', time.strftime('%d-%b-%Y', tmdat))
                    elif ent.is_dir(follow_symlinks=True):
                        targetname = os.path.normpath(os.path.join(dirname, linkname))
                        file = dir.files.get(ent.name)
                        if file is None:
                            file = File(ent.name, dir)
                            file.complete(['Symlink to '+targetname])
                        file.putkey('islink', True)
                        file.putkey('islinkdir', True)
                        file.putkey('linkdir', targetname)

                    continue
                        
                if ent.is_file():
                    if ent.name == 'Index':
                        continue
                    file = dir.files.get(ent.name)
                    if file is None:
                        if noindexlist.check(dirname2):
                            continue
                        file = File(ent.name, dir)
                    file.putkey('filesize', str(sta.st_size))
                    file.putkey('date', str(int(sta.st_mtime)))
                    tmdat = time.gmtime(sta.st_mtime)
                    file.putkey('datestr', time.strftime('%d-%b-%Y', tmdat))
                    hash_md5, hash_sha512 = hasher.get_hashes(pathname, sta.st_size, int(sta.st_mtime))
                    file.putkey('md5', hash_md5)
                    file.putkey('sha512', hash_sha512)
                    continue

                if ent.is_dir():
                    dir2 = dirmap.get(dirname2)
                    if dir2 is None:
                        dir2 = Directory(dirname2, dirmap=dirmap)
                    file = dir.files.get(ent.name)
                    if file is not None:
                        file.putkey('linkdir', dirname2)
                    if parentlist and parentdir:
                        parentname = os.path.join(parentdir, ent.name)
                        parentfile = parentlist.get(parentname)
                        if parentfile is not None:
                            parentfile.putkey('linkdir', dirname2)
                    scan_directory(dirname2, dir.files, ent.name)
                    continue
                            
            # End of internal scan_directory function.

        # Call the above function recursively.
        scan_directory(ROOTNAME)

    if opts.verbose:
        print('Creating subdirectory lists and counts...')
            
    # Create the subdir list and count for each directory.
    for dir in dirmap.values():
        if dir.parentdirname:
            dir2 = dirmap.get(dir.parentdirname)
            if not dir2:
                sys.stderr.write('Directory\'s parent is not listed: %s\n' % (dir.dir))
                continue
            dir.parentdir = dir2
            dir2.subdirs[dir.dir] = dir
                
    for dir in dirmap.values():
        dir.putkey('count', len(dir.files))
        dir.putkey('subdircount', len(dir.subdirs))
        
    return dirmap

def check_missing_files(dirmap):
    """Go through dirmap and look for entries which were not found in
    the scan-directory phase. We know an entry was not found if we
    never read its date (file timestamp).
    """
    for dir in dirmap.values():
        for file in dir.files.values():
            if file.getkey('date') is None and file.getkey('linkdir') is None and file.getkey('islink') is None:
                sys.stderr.write('Index entry without file: %s/%s\n' % (dir.dir, file.name))

def parity_flip(map):
    """Utility function to change the "parity" entry in a dict from "Even"
    to "Odd" and vice versa. Call this at the top of a loop. The dict
    should start with no "parity" entry.
    """
    val = map.get('parity')
    if val == 'Even':
        map['parity'] = 'Odd'
    else:
        map['parity'] = 'Even'

def generate_output_dirlist(dirmap):
    """Write out the dirlist.html index.
    """
    filename = plan.get('Dir-List-Template')
    dirlist_body = read_lib_file(filename, '<html><body>\n{_dirs}\n</body></html>\n')

    dirlist_entry = plan.get('Dir-List-Entry', '<li>{dir}')
    
    filename = plan.get('General-Footer')
    general_footer = read_lib_file(filename, '')

    def dirlist_thunk(outfl):
        dirlist = list(dirmap.values())
        dirlist.sort(key=lambda dir:dir.dir.lower())
        itermap = {}
        for dir in dirlist:
            parity_flip(itermap)
            Template.substitute(dirlist_entry, ChainMap(itermap, dir.submap), outfl=outfl)
            outfl.write('\n')
            
    relroot = '..'
    general_footer_thunk = lambda outfl: Template.substitute(general_footer, ChainMap(plan.map, { 'relroot':relroot }), outfl=outfl)

    itermap = { '_dirs':dirlist_thunk, 'footer':general_footer_thunk, 'rootdir':ROOTNAME, 'relroot':relroot }

    filename = os.path.join(DESTDIR, 'dirlist.html')
    tempname = os.path.join(DESTDIR, '__temp')
    writer = SafeWriter(tempname, filename)
    Template.substitute(dirlist_body, ChainMap(itermap, plan.map), outfl=writer.stream())
    writer.resolve()
    
def generate_output_datelist(dirmap):
    """Write out the date.html indexes.
    """
    intervals = [
        (0, 0, None),
        (1, 7*24*60*60, 'week'),
        (2, 31*24*60*60, 'month'),
        (3, 93*24*60*60, 'three months'),
        (4, 366*24*60*60, 'year')
    ]

    # Create a list of all files is sorted by date, newest to oldest.
    
    filelist = []
    for dir in dirmap.values():
        for file in dir.files.values():
            if file.getkey('date'):
                filelist.append(file)

    # We're sorting by date, but there are cases where files have exactly
    # the same timestamp. (Possibly because one is a symlink to the other!)
    # In those cases, we have a secondary sort key of filename, and then
    # a tertiary key of directory name.
    filelist.sort(key=lambda file: (-int(file.getkey('date')), file.name.lower(), file.path.lower()))

    filename = plan.get('Date-List-Template')
    datelist_body = read_lib_file(filename, '<html><body>\n{_files}\n</body></html>\n')

    datelist_entry = plan.get('Date-List-Entry', '<li>{name}')

    filename = plan.get('General-Footer')
    general_footer = read_lib_file(filename, '')

    curtime = int(time.time())
    
    for (intkey, intlen, intname) in intervals:
        if intkey:
            filename = os.path.join(DESTDIR, 'date_%d.html' % (intkey,))
        else:
            filename = os.path.join(DESTDIR, 'date.html')

        relroot = '..'
        
        def filelist_thunk(outfl):
            itermap = { 'relroot':relroot }
            for file in filelist:
                parity_flip(itermap)
                if intlen:
                    if int(file.getkey('date')) + intlen < curtime:
                        break
                Template.substitute(datelist_entry, ChainMap(itermap, file.submap), outfl=outfl)
                outfl.write('\n')
                
        general_footer_thunk = lambda outfl: Template.substitute(general_footer, ChainMap(plan.map, { 'relroot':relroot }), outfl=outfl)
        
        itermap = { '_files':filelist_thunk, 'footer':general_footer_thunk, 'rootdir':ROOTNAME, 'relroot':relroot }
        if intname:
            itermap['interval'] = intname
            
        tempname = os.path.join(DESTDIR, '__temp')
        writer = SafeWriter(tempname, filename)
        Template.substitute(datelist_body, ChainMap(itermap, plan.map), outfl=writer.stream())
        writer.resolve()
    
def generate_output_indexes(dirmap):
    """Write out the general (per-directory) indexes.
    """
    global xify_mode
    
    filename = plan.get('Main-Template')
    main_body = read_lib_file(filename, '<html>Missing main template!</html>')

    filename = plan.get('Top-Level-Template')
    toplevel_body = read_lib_file(filename, 'Welcome to the archive.\n')

    filename = plan.get('General-Footer')
    general_footer = read_lib_file(filename, '')

    filelist_entry = plan.get('File-List-Entry', '<li>{name}\n{desc}')
    subdirlist_entry = plan.get('Subdir-List-Entry', '<li>{dir}')
    dirlinkelement_body = plan.get('Dir-Link-Element', '')
    
    for dir in dirmap.values():
        filename = os.path.join(DESTDIR, xify_dirname(dir.dir)+'.html')
        
        relroot = '..'
        
        def dirlinks_thunk(outfl):
            els = dir.dir.split('/')
            val = ''
            first = True
            for el in els:
                if first:
                    val = el
                else:
                    val = val + '/' + el
                itermap = { 'dir':val, 'name':el, 'first':first, 'relroot':relroot }
                Template.substitute(dirlinkelement_body, itermap, outfl=outfl)
                first = False
            
        def filelist_thunk(outfl):
            filelist = list(dir.files.values())
            filelist.sort(key=lambda file:file.name.lower())
            itermap = { 'relroot':relroot }
            for file in filelist:
                parity_flip(itermap)
                Template.substitute(filelist_entry, ChainMap(itermap, file.submap), outfl=outfl)
                outfl.write('\n')
        
        def subdirlist_thunk(outfl):
            dirlist = list(dir.subdirs.values())
            dirlist.sort(key=lambda dir:dir.dir.lower())
            itermap = { 'relroot':relroot }
            for subdir in dirlist:
                parity_flip(itermap)
                Template.substitute(subdirlist_entry, ChainMap(itermap, subdir.submap), outfl=outfl)
                outfl.write('\n')

        general_footer_thunk = lambda outfl: Template.substitute(general_footer, ChainMap(dir.submap, { 'relroot':relroot }), outfl=outfl)
        toplevel_body_thunk = lambda outfl: Template.substitute(toplevel_body, ChainMap(dir.submap, { 'relroot':relroot }), outfl=outfl)
        
        itermap = { '_files':filelist_thunk, '_subdirs':subdirlist_thunk, '_dirlinks':dirlinks_thunk, 'footer':general_footer_thunk, 'rootdir':ROOTNAME, 'relroot':relroot }
        if dir.dir == ROOTNAME:
            itermap['hasdesc'] = True
            itermap['header'] = toplevel_body_thunk

        # Write out the Xdir.html version
        xify_mode = True
        tempname = os.path.join(DESTDIR, '__temp')
        writer = SafeWriter(tempname, filename)
        Template.substitute(main_body, ChainMap(itermap, dir.submap), outfl=writer.stream())
        writer.resolve()

        # Write out the dir/index.html version
        xify_mode = False
        relroot = relroot_for_dirname(dir.dir)
        itermap['relroot'] = relroot
        filename = os.path.join(DESTDIR, dir.dir, 'index.html')
        writer = SafeWriter(tempname, filename)
        Template.substitute(main_body, ChainMap(itermap, dir.submap), outfl=writer.stream())
        writer.resolve()


def generate_output_xml(dirmap):
    """Write out the Master-Index.xml file.
    """
    filename = plan.get('XML-Template')
    xmllist_body = read_lib_file(filename, '<xml>\n{_dirs}\n</xml>\n')

    filename = plan.get('XML-Dir-Template')
    dirlist_entry = read_lib_file(filename, '<directory>\n{dir}\n</directory>\n')
    
    filename = plan.get('XML-File-Template')
    filelist_entry = read_lib_file(filename, '<file>\n{name}\n</file>\n')

    def dirlist_thunk(outfl):
        dirlist = list(dirmap.values())
        dirlist.sort(key=lambda dir:dir.dir.lower())
        
        for dir in dirlist:
            def filelist_thunk(outfl):
                filelist = list(dir.files.values())
                filelist.sort(key=lambda file:file.name.lower())
                itermap = {}
                for file in filelist:
                    Template.substitute(filelist_entry, ChainMap(itermap, file.submap), outfl=outfl)
                    outfl.write('\n')

            itermap = { '_files':filelist_thunk }
            Template.substitute(dirlist_entry, ChainMap(itermap, dir.submap), outfl=outfl)
        
    itermap = { '_dirs':dirlist_thunk }
    
    filename = os.path.join(DESTDIR, 'Master-Index.xml')
    tempname = os.path.join(DESTDIR, '__temp')
    writer = SafeWriter(tempname, filename)
    Template.substitute(xmllist_body, ChainMap(itermap, plan.map), outfl=writer.stream())
    writer.resolve()

def generate_output(dirmap):
    """Write out all the index files.
    """
    global xify_mode
    
    if not os.path.exists(DESTDIR):
        os.mkdir(DESTDIR)
        
    dirlist = list(dirmap.values())
    for dir in dirlist:
        dirname = os.path.join(DESTDIR, dir.dir)
        os.makedirs(dirname, exist_ok=True)

    if opts.verbose:
        print('Generating output...')

    xify_mode = False
    generate_output_dirlist(dirmap)
    generate_output_datelist(dirmap)
    generate_output_indexes(dirmap)
    generate_output_xml(dirmap)

def generate_metadata(dirmap):
    """Write out all the metadata files.
    """
    if not opts.treedir:
        metadir = os.path.join('.', opts.metadir)
    else:
        metadir = os.path.join(opts.treedir, opts.metadir)

    if not os.path.exists(metadir):
        os.mkdir(metadir)
        
    dirlist = list(dirmap.values())
    for dir in dirlist:
        dirname = os.path.join(metadir, dir.dir)
        os.makedirs(dirname, exist_ok=True)

    if opts.verbose:
        print('Generating metadata...')

    for dir in dirlist:
        dirname = os.path.join(metadir, dir.dir)
        tempname = os.path.join(dirname, '__temp')
        
        for filename, file in dir.files.items():
            filebase = os.path.join(dirname, filename)
            
            if not file.metadata:
                if os.path.exists(filebase+'.txt'):
                    os.remove(filebase+'.txt')
                if os.path.exists(filebase+'.json'):
                    os.remove(filebase+'.json')
                if os.path.exists(filebase+'.xml'):
                    os.remove(filebase+'.xml')
                continue
            
            writer = SafeWriter(tempname, filebase+'.txt')
            writer.stream().write('# %s/%s\n' % (dir.dir, filename,))
            for key, val in file.metadata.items():
                writer.stream().write('%s: %s\n' % (key, val,))
            writer.resolve()


# Begin work!
# We only do this if we're the executing script. If this is just an imported
# module, we do no work. (This lets the test script "import ifmap" for unit
# tests.)

if __name__ == '__main__':
    (opts, args) = popt.parse_args()

    if not opts.libdir:
        raise Exception('--src argument required')

    plan = ParamFile(os.path.join(opts.libdir, 'index'))
    
    hasher = FileHasher()
    noindexlist = NoIndexEntry()
    
    Template.addfilter('html', escape_html_string)
    Template.addfilter('slashwbr', slash_add_wbr)
    Template.addfilter('url', escape_url_string)
    Template.addfilter('xify', xify_dirname)
    Template.addfilter('indexuri', indexuri_dirname)
    Template.addfilter('plural_s', pluralize_s)
    Template.addfilter('plural_ies', pluralize_ies)

    converter = markdown.Markdown(extensions = [])
    convertermeta = markdown.Markdown(extensions = ['meta'])
    
    if not opts.treedir:
        DESTDIR = os.path.join('.', opts.destdir)
    else:
        DESTDIR = os.path.join(opts.treedir, opts.destdir)
        
    dirmap = parse_master_index(opts.indexpath, opts.treedir)
    
    check_missing_files(dirmap)
    
    generate_output(dirmap)
    generate_metadata(dirmap)
    
