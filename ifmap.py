#!/usr/bin/env python3

import sys
import re
import os
import os.path
import time
import datetime
import hashlib
from collections import ChainMap, OrderedDict
import optparse
import markdown
import json

from jinja2 import Environment, FileSystemLoader, select_autoescape
from jinja2.ext import Extension

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
popt.add_option('-v', '--verbose',
                action='store_true', dest='verbose',
                help='print verbose output')
popt.add_option('--curdate',
                action='store', dest='curdate', metavar='ISODATE',
                help='timestamp to use as "now" (for testing)')

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
    {[bar}repeat-{bar:value}...{]}: Repeat through map['bar'], which
        must be a list/tuple. The body will be repeated with {bar:value}
        substituted in. Filters may be used. {bar:first} will be true
        on the first iteration.
    {}: No-op, substitutes the empty string.

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
        return template
    
    def __init__(self, body):
        if type(body) is list:
            self.ls = body
            return
        
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
            elif val.startswith('['):
                tag = TemplateTag(val[1:], 'repeat')
            elif val == ']':
                tag = TemplateTag(None, 'endrepeat')
            elif val == '':
                tag = TemplateTag('')
            else:
                args = None
                if '|' in val:
                    args = val.split('|')
                    args = [ el.strip() for el in args if el.strip() ]
                    val = args.pop(0)
                tag = TemplateTag(val, 'var', args)
            self.ls.append(tag)

        depths = []
        for pos in range(len(self.ls)):
            tag = self.ls[pos]
            if tag.type == 'repeat':
                depths.append(pos)
            elif tag.type == 'endrepeat':
                if not depths:
                    print('Problem: unmatched endrepeat-tag')
                else:
                    val = depths.pop()
                    self.ls[val].args = [ pos-val ]
        if depths:
            print('Problem: unmatched repeat-tag')
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
            elif tag.type == 'repeat':
                ls.append('{[%s}' % (tag.value,))
            elif tag.type == 'endrepeat':
                ls.append('{]}')
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
        
        for (pos, tag) in enumerate(self.ls):
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
            elif tag.type == 'repeat':
                if activelist[-1]:
                    val = None
                    if map:
                        val = map.get(tag.value)
                    if val is None:
                        outfl.write('[UNKNOWN]')
                        print('Problem: undefined brace-tag: %s' % (tag.value,))
                    elif type(val) in (list, tuple):
                        subls = self.ls[pos+1 : pos+tag.args[0]]
                        subtemplate = Template(subls)
                        valuekey = tag.value+':value'
                        firstkey = tag.value+':first'
                        submap = ChainMap({ firstkey:True }, map)
                        for subval in val:
                            submap[valuekey] = subval
                            subtemplate.subst(submap, outfl=outfl)
                            submap[firstkey] = False
                    elif type(val) in (dict, OrderedDict):
                        subls = self.ls[pos+1 : pos+tag.args[0]]
                        subtemplate = Template(subls)
                        keykey = tag.value+':key'
                        valuekey = tag.value+':value'
                        firstkey = tag.value+':first'
                        submap = ChainMap({ firstkey:True }, map)
                        for subkey, subval in val.items():
                            submap[keykey] = subkey
                            submap[valuekey] = subval
                            subtemplate.subst(submap, outfl=outfl)
                            submap[firstkey] = False
                    else:
                        outfl.write('[NOT-REPEATABLE]')
                        print('Problem: unrepeatable tag type: %s=%r' % (tag.value, val))
                activelist.append(False)
            elif tag.type == 'endrepeat':
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
        lastkey = None
        
        fl = open(filename, encoding='utf-8')
        while True:
            ln = fl.readline()
            if not ln:
                break
            ln = ln.rstrip()
            if not ln:
                break
            if ln.startswith('    '):
                if not lastkey:
                    print('Problem: header line start with continuation: %s' % (ln,))
                    continue
                self.map[lastkey] = self.map[lastkey] + '\n' + ln.strip()
                continue
            key, dummy, val = ln.partition(':')
            if not dummy:
                print('Problem: no colon in header line: %s' % (ln,))
                continue
            key = key.strip()
            lastkey = key
            self.map[key] = val.strip()

        self.body = fl.read()
        fl.close()

    def get(self, key, default=None):
        return self.map.get(key, default)

    def put(self, key, val):
        self.map[key] = val

class DirList:
    """DirList: A list of directories, loaded from a source file.
    """
    def __init__(self, filename):
        self.ls = []
        self.set = set()
        try:
            filename = os.path.join(opts.libdir, filename)
            fl = open(filename, encoding='utf-8')
        except:
            return
        while True:
            ln = fl.readline()
            if not ln:
                break
            ln = ln.strip()
            if not ln:
                continue
            self.ls.append(ln)
            self.set.add(ln)
        fl.close()
    
class NoIndexEntry(DirList):
    """NoIndexEntry: A list of directories in which it's okay that there's
    no index entries.

    The logic here is a bit twisty. Normally, if we find a file which
    is not mentioned in any Index file, we print a warning.

    The no-index-entry file (in libdir) is a list of files and directories
    in which we do *not* do this check (and therefore print no warning,
    and never exclude files). We use this for directories containing a
    large number of boring files (like info/ifdb), and directories whose
    contents change frequently (like unprocessed).
    """
    def __init__(self):
        DirList.__init__(self, 'no-index-entry')

    def check(self, path):
        """The argument is the pathname of a file which was found in
        the treedir but which was never mentioned in any Index file.
        
        If the path, or any prefix of the path, exists in our list,
        we return True.
        """
        for val in self.ls:
            if path.startswith(val):
                return True
        return False
    
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

def isodate(val):
    """Convert a timestamp to RFS date format.
    """
    tup = time.gmtime(int(val))
    # RFC 822 date format.
    return time.strftime('%a, %d %b %Y %H:%M:%S +0000', tup)
    
def indexuri_dirname(val):
    """Convert a directory name to the URI for its index file.
    (This used to implement the X trick, but we've dropped that.)
    """
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

def pluralize(val, singular='', plural='s'):
    if val == 1 or val == '1':
        return singular
    else:
        return plural

### will go away? ###
def pluralize_s(val):
    if val == 1 or val == '1':
        return ''
    else:
        return 's'

### will go away? ###
def pluralize_ies(val):
    if val == 1 or val == '1':
        return 'y'
    else:
        return 'ies'

### will go away? ###
def slash_add_wbr(val):
    """Add a silent wordwrap-point after every slash.
    """
    return val.replace('/', '/<wbr>')

def escape_wikipage(val):
    """Convert a wiki page title to its URI form. I think this just
    means converting spaces to underscores.
    (This does *not* include percent-encoding; that's a later stage.)
    """
    return val.replace(' ', '_')

### will go away? ###
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

urlable_pattern = re.compile('[,-;@-z]+')

def escape_url_string(val):
    """Apply URL escaping (percent escapes) to a string.
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
            for chenc in ch.encode('utf8'):
              res.append('%%%02X' % (chenc,))
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

class ArchiveTree:
    """ArchiveTree: The big directory map.
    """
    def __init__(self):
        self.dirmap = {}

    def get_directory(self, dirname, oradd=False):
        dir = self.dirmap.get(dirname)
        if dir:
            return dir
        if oradd:
            dir = Directory(dirname)
            self.dirmap[dirname] = dir
            return dir
        return None

class Directory:
    """Directory: one directory in the big directory map.
    """
    def __init__(self, dirname):
        self.dir = dirname
        self.submap = {}

        self.putkey('dir', dirname)

        pos = dirname.rfind('/')
        if pos < 0:
            self.parentdirname = None
            self.barename = dirname
        else:
            parentdirname = dirname[ 0 : pos ]
            self.parentdirname = parentdirname
            self.barename = dirname[ pos+1 : ]
            self.putkey('parentdir', parentdirname)

        # To be filled in later
        self.files = {}
        self.subdirs = {}
        self.parentdir = None
        self.metadata = OrderedDict()

    def __repr__(self):
        return '<Directory %s>' % (self.dir,)

    def getkey(self, key, default=None):
        return self.submap.get(key)
    
    def putkey(self, key, val):
        self.submap[key] = val

    def getitems(self, isdir=False, display=True):
        ls = list(self.files.values())
        if display:
            # When displaying, symlinks and deep refs to directories all
            # count as directories.
            ls = [ file for file in ls if file.isdir == isdir ]
        else:
            # For XML cataloging, symlinks are always files. Deep refs
            # are skipped entirely, sorry.
            ls = [ file for file in ls if not file.isdeep and (file.isdir and not file.islink) == isdir ]
        return ls

metadata_pattern = re.compile('^[ ]*[a-zA-Z0-9_-]+:')
unbox_suffix_pattern = re.compile('\.(tar\.gz|tgz|tar\.z|zip)$', re.IGNORECASE)

def stripmetadata(lines):
    """Given a list of lines, remove the metadata lines (lines at the
    beginning that look like "key:value"). Return a joined string of
    the rest.
    """
    pos = 0
    for ln in lines:
        if not ln.strip():
            break
        if not (metadata_pattern.match(ln) or ln.startswith('    ')):
            break
        pos += 1
    val = '\n'.join(lines[pos:])
    return val.rstrip() + '\n'

def deepsplit(ls):
    """Split a list of File objects into non-deep and deep lists.
    """
    undeepls = []
    deepls = []
    for val in ls:
        if val.isdeep:
            deepls.append(val)
        else:
            undeepls.append(val)
    return undeepls, deepls
        
class File:
    """File: one entry in a directory.
    The name is a bit of a misnomer; this could represent a file,
    symlink, or subdirectory.
    (There is no global file list. You have to look at dir.files for each
    directory in dirmap.)
    """
    def __init__(self, filename, parentdir, isdir=False, islink=False):
        self.submap = {}
        self.parentdir = parentdir
        # Place into the parent directory.
        parentdir.files[filename] = self

        self.name = filename
        self.path = parentdir.dir+'/'+filename
        self.metadata = OrderedDict()
        self.isdir = isdir
        self.islink = islink
        self.isdeep = ('/' in filename)

        self.intree = False
        self.inmaster = False
        self.putkey('name', filename)
        self.putkey('dir', parentdir.dir)
        self.putkey('path', self.path)

        if not islink:
            if isdir:
                self.putkey('isdir', True)
        else:
            self.putkey('islink', True)
            if isdir:
                self.putkey('islinkdir', True)
            else:
                self.putkey('islinkfile', True)

    def __repr__(self):
        linkstr = ' (link)' if self.islink else ''
        dirstr = ' (dir)' if self.isdir else ''
        return '<File %s%s%s>' % (self.name, linkstr, dirstr,)

    def complete(self, desclines):
        # Take the accumulated description text and stick it into our
        # File object.
        if desclines:
            val = '\n'.join(desclines)
            filestr = convertermeta.convert(val)
            for (mkey, mls) in convertermeta.Meta.items():
                self.metadata[mkey] = list(mls)
            convertermeta.Meta.clear()
            ### sort metadata?
            self.putkey('hasmetadata', bool(self.metadata))
            
            self.putkey('desc', filestr)
            self.putkey('hasdesc', is_string_nonwhite(filestr))

            # Remove metadata lines before generating XML.
            descstr = stripmetadata(desclines)
            self.putkey('xmldesc', descstr)
            self.putkey('hasxmldesc', is_string_nonwhite(descstr))

    def getkey(self, key, default=None):
        return self.submap.get(key)
    
    def putkey(self, key, val):
        self.submap[key] = val

    def getmetadata_string(self, key):
        # Return a metadata value as a string. If there are multiple values,
        # just use the first.
        if key not in self.metadata or not self.metadata[key]:
            return None
        return self.metadata[key][0]

def parse_master_index(indexpath, archtree):
    """Read through the Master-Index file and create directories and files.
    """
    
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

                headerstr = '\n'.join(headerlines)
                headerstr = headerstr.rstrip() + '\n'
                # Now headerstr starts with zero newlines and ends
                # with one newline.
                anyheader = bool(headerstr.strip())
                dir.putkey('hasdesc', anyheader)
                dir.putkey('hasxmldesc', anyheader)
                if anyheader:
                    # Convert Markdown to HTML.
                    val = convertermeta.convert(headerstr)
                    for (mkey, mls) in convertermeta.Meta.items():
                        dir.metadata[mkey] = list(mls)
                    convertermeta.Meta.clear()
                    ### sort metadata?
                    dir.putkey('hasmetadata', bool(dir.metadata))
                    dir.putkey('headerormeta', (bool(dir.metadata) or bool(val)))
                    dir.putkey('header', val)
                    # For XML, we just escape.
                    val = stripmetadata(headerstr.split('\n'))
                    dir.putkey('xmlheader', val)
                dir = None

            if not done:
                # Beginning of a directory block.
                assert(match is not None)
                dirname = match.group(1)
                if opts.verbose:
                    print('Starting  %s...' % (dirname,))
                dir = archtree.get_directory(dirname, oradd=True)
                
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
            # (If the file already exists, then it was found in the tree;
            # we'll add to its entry. If not, we create a new entry,
            # presumed to be as regular file.)

            filename = bx[2:].strip()
            bx = ''
            filedesclines = []

            if '/' not in filename:
                file = dir.files.get(filename)
                if file is None:
                    file = File(filename, dir)
                file.inmaster = True
            else:
                # Distant file reference, like "Comp/Games"
                reldir, _, relfile = filename.rpartition('/')
                reldir = dir.dir+'/'+reldir
                rel = archtree.get_directory(reldir, oradd=False)
                if not rel:
                    sys.stderr.write('Compound file entry refers to a bad directory: "%s" in %s' % (filename, dir.dir,))
                    continue
                relfile = rel.files.get(relfile)
                if not relfile:
                    sys.stderr.write('Compound file entry refers to a bad file: "%s" in %s' % (filename, dir.dir,))
                    continue
                relfile.inmaster = True
                file = dir.files.get(filename)
                if file is not None:
                    sys.stderr.write('Compound file entry appears twice: "%s" in %s' % (filename, dir.dir,))
                    continue
                file = File(filename, dir, isdir=relfile.isdir, islink=relfile.islink)
                if file.isdir:
                    file.putkey('linkdir', dir.dir+'/'+filename)
            continue

        # Continuing a file block.
        filedesclines.append(bx)

    # Finished reading Master-Index.
    infl.close()

def parse_directory_tree(treedir, archtree):
    """Do a scan of the actual file tree and create directories and
    files. We also take the opportunity to scan file dates and sizes.
    """

    def scan_directory(dirname, parentlist=None, parentdir=None):
        """Internal recursive function.
        """
        if opts.verbose:
            print('Scanning %s...' % (dirname,))
        dir = archtree.get_directory(dirname, oradd=True)
        
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
                        file = File(ent.name, dir, islink=True, isdir=False)
                    file.intree = True
                    file.putkey('linkpath', linkname)
                    file.putkey('nlinkpath', os.path.normpath(os.path.join(dir.dir, linkname)))
                    file.putkey('date', str(int(sta2.st_mtime)))
                    tmdat = time.gmtime(sta2.st_mtime)
                    file.putkey('datestr', time.strftime('%d-%b-%Y', tmdat))
                elif ent.is_dir(follow_symlinks=True):
                    targetname = os.path.normpath(os.path.join(dirname, linkname))
                    file = dir.files.get(ent.name)
                    if file is None:
                        file = File(ent.name, dir, islink=True, isdir=True)
                        #file.complete(['Symlink to '+targetname])
                    file.intree = True
                    file.putkey('linkdir', targetname)

                continue
                    
            if ent.is_file():
                if ent.name == 'Index':
                    continue
                file = dir.files.get(ent.name)
                if file is None:
                    file = File(ent.name, dir)
                file.intree = True
                file.putkey('filesize', str(sta.st_size))
                file.putkey('date', str(int(sta.st_mtime)))
                tmdat = time.gmtime(sta.st_mtime)
                file.putkey('datestr', time.strftime('%d-%b-%Y', tmdat))
                hash_md5, hash_sha512 = hasher.get_hashes(pathname, sta.st_size, int(sta.st_mtime))
                file.putkey('md5', hash_md5)
                file.putkey('sha512', hash_sha512)
                continue

            if ent.is_dir():
                dir2 = archtree.get_directory(dirname2, oradd=True)
                file = dir.files.get(ent.name)
                if file is None:
                    file = File(ent.name, dir, isdir=True)
                file.putkey('linkdir', dirname2)
                file.intree = True
                scan_directory(dirname2, dir.files, ent.name)
                continue
                        
        # End of internal scan_directory function.

    # Call the above function recursively.
    scan_directory(ROOTNAME)
    
def construct_archtree(indexpath, treedir):
    """Parse the Master-Index file, and then go through the directory
    tree to find more files. Return all the known directories as a dict.

    Either or both arguments may be None. At a bare minimum, this always
    returns the root directory.
    """

    archtree = ArchiveTree()

    rootdir = archtree.get_directory(ROOTNAME, oradd=True)

    if treedir:
        parse_directory_tree(treedir, archtree)

    if indexpath:
        parse_master_index(indexpath, archtree)

    if opts.verbose:
        print('Creating subdirectory lists and counts...')
            
    # Create the subdir list.
    for dir in archtree.dirmap.values():
        if dir.parentdirname:
            dir2 = archtree.get_directory(dir.parentdirname, oradd=False)
            if not dir2:
                sys.stderr.write('Directory\'s parent is not listed: %s\n' % (dir.dir))
                continue
            dir.parentdir = dir2
            dir2.subdirs[dir.dir] = dir

            fdir = dir2.files.get(dir.barename)
            if fdir.submap.get('hasdesc'):
                dir.putkey('hasparentdesc', True)
                dir.putkey('parentdesc', fdir.submap.get('desc'))
                
    return archtree

def check_missing_files(dirmap):
    """Go through dirmap and look for entries which were not found in
    the scan-directory phase.
    Also look for files that *were* in the scan-directory phase, but
    had no Index entry.
    """
    for dir in dirmap.values():
        for file in dir.files.values():
            if file.inmaster and not file.intree and file.getkey('linkdir') is None and file.getkey('islink') is None:
                val = file.name
                if file.isdeep:
                    val = '(%s)' % (val,)
                sys.stderr.write('Index entry without file: %s/%s\n' % (dir.dir, val,))
            if file.intree and not file.inmaster and file.getkey('linkdir') is None:
                if not noindexlist.check(file.path):
                    sys.stderr.write('File without index entry: %s\n' % (file.path,))


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

def generate_output_dirlist(dirmap, jenv):
    """Write out the dirlist.html index.
    """
    template = jenv.get_template('dirlist.html')

    dirlist = list(dirmap.values())
    dirlist.sort(key=lambda dir:dir.dir.lower())
    finaldirlist = [ dir.submap for dir in dirlist ]
            
    itermap = {
        'title': 'Complete Index of Directories',
        'pageid': 'dirpage',
        '_dirs': finaldirlist,
        'rootdir': ROOTNAME,
    }

    filename = os.path.join(DESTDIR, 'dirlist.html')
    tempname = os.path.join(DESTDIR, '__temp')
    writer = SafeWriter(tempname, filename)
    template.stream(itermap).dump(writer.stream())
    writer.resolve()
    
def generate_output_dirmap(dirmap, jenv):
    """Write out the dirlist.html index.
    """
    skiplist = [ re.compile(val) for val in mapskippatternlist.ls ]
    
    template = jenv.get_template('dirmap.html')

    finaldirlist = []
    dirlist = list(dirmap.values())
    dirlist.sort(key=lambda dir:dir.dir.lower())
    itermap = {}
    for dir in dirlist:
        skip = False
        for pat in skiplist:
            if pat.match(dir.dir):
                skip = True
                break
        if not skip:
            finaldirlist.append(dir.submap)

    itermap = {
        'title': 'Index of Directories',
        'pageid': 'dirpage',
        '_dirs': finaldirlist,
        'rootdir': ROOTNAME,
    }

    filename = os.path.join(DESTDIR, 'dirmap.html')
    tempname = os.path.join(DESTDIR, '__temp')
    writer = SafeWriter(tempname, filename)
    template.stream(itermap).dump(writer.stream())
    writer.resolve()
    
def generate_output_datelist(dirmap, jenv):
    """Write out the date.html indexes.
    """
    intervals = [
        (0, 0, None),
        (1, 7*24*60*60, 'week'),
        (2, 31*24*60*60, 'month'),
        (3, 93*24*60*60, 'three months'),
        (4, 366*24*60*60, 'year')
    ]

    template = jenv.get_template('datelist.html')
    
    # Create a list of all files sorted by date, newest to oldest.
    
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

    for (intkey, intlen, intname) in intervals:
        if intkey:
            filename = os.path.join(DESTDIR, 'date_%d.html' % (intkey,))
        else:
            filename = os.path.join(DESTDIR, 'date.html')

        relroot = '..'

        finalfilelist = []
        for file in filelist:
            if intlen:
                if int(file.getkey('date')) + intlen < curdate:
                    break
            finalfilelist.append(file.submap)
                
        itermap = {
            'pageid': 'datepage',
            '_files': finalfilelist,
            'rootdir': ROOTNAME,
        }
        if intname:
            itermap['interval'] = intname
            itermap['title'] = 'Files by Date (past %s)' % (intname,)
        else:
            itermap['title'] = 'All Files by Date'
            
        tempname = os.path.join(DESTDIR, '__temp')
        writer = SafeWriter(tempname, filename)
        template.stream(itermap).dump(writer.stream())
        writer.resolve()
    
def generate_output_indexes(dirmap):
    """Write out the general (per-directory) indexes.
    """
    template = jenv.get_template('main.html')
    
    for dir in dirmap.values():
        relroot = '..'

        # Divide up the directory's items into "files" and "subdirs".
        # Note that we're not using dir.subdirs here; we're relying on
        # dir.files and distinguishing the Files based on their flags.
        filelist = dir.getitems(isdir=False, display=True)
        filelist.sort(key=lambda file:file.name.lower())
        subdirlist = dir.getitems(isdir=True, display=True)
        subdirlist.sort(key=lambda file:file.name.lower())

        # Divide each of these lists into  "regular" and "deep sublists.
        filelist, alsofilelist = deepsplit(filelist)
        subdirlist, alsosubdirlist = deepsplit(subdirlist)

        dirlinkels = []
        els = dir.dir.split('/')
        for ix in range(0, len(els)):
            dirlinkels.append( ('/'.join(els[:ix+1]), els[ix]) )
            
        def prepare_filelist(fls):
            res = []
            for file in fls:
                itermap = {}

                # We show the unbox link based on the "unbox-link"
                # metadata key ("true" or otherwise). If that's not
                # present, we check whether the parent dir is listed in
                # no-unbox-link. Failing that, we default to showing it
                # for zip/tar.gz/tgz files.
                val = file.getmetadata_string('unbox-link')
                if val:
                    flag = (val.lower() == 'true')
                elif file.parentdir.dir in nounboxlinklist.set:
                    flag = False
                else:
                    flag = bool(unbox_suffix_pattern.search(file.name))
                # But if "unbox-block" is set, definitely no link.
                # (Unbox pays attention to "unbox-block" and refuses to
                # unbox the file. "unbox-link:false" only affects the
                # index page.)
                if file.getmetadata_string('unbox-block') == 'true':
                    flag = false
                if flag:
                    itermap['hasunboxlink'] = True
                    
                if file.metadata:
                    itermap['_metadata'] = file.metadata
                res.append(ChainMap(itermap, file.submap))
            return res

        itermap = {
            'pageid': 'indexpage',
            'title': 'Index: ' + dir.dir,
            'count': len(filelist), 'subdircount': len(subdirlist),
            'alsocount': len(alsofilelist), 'alsosubdircount': len(alsosubdirlist),
            '_files': prepare_filelist(filelist),
            '_alsofiles': prepare_filelist(alsofilelist),
            '_subdirs': [ sdir.submap for sdir in subdirlist ],
            '_alsosubdirs': [ sdir.submap for sdir in alsosubdirlist ],
            '_dirlinkels': dirlinkels,
            'rootdir': ROOTNAME,
        }
        if dir.metadata:
            itermap['_metadata'] = dir.metadata

        tempname = os.path.join(DESTDIR, '__temp')
        relroot = relroot_for_dirname(dir.dir)
        itermap['relroot'] = relroot
        filename = os.path.join(DESTDIR, dir.dir, 'index.html')
        writer = SafeWriter(tempname, filename)
        template.stream(ChainMap(itermap, dir.submap)).dump(writer.stream())
        writer.resolve()


def generate_output_xml(dirmap, jenv):
    """Write out the Master-Index.xml file.
    """
    template = jenv.get_template('xmlbase.xml')

    dirlist = list(dirmap.values())
    dirlist.sort(key=lambda dir:dir.dir.lower())

    dirents = []
    for dir in dirlist:
        filelist = dir.getitems(isdir=False, display=False)
        filelist.sort(key=lambda file:file.name.lower())
        subdirlist = dir.getitems(isdir=True, display=False)
        subdirlist.sort(key=lambda file:file.name.lower())

        fileentlist = []
        for file in filelist:
            itermap = { '_metadata': list(file.metadata.items()) }
            fileentlist.append(ChainMap(itermap, file.submap))

        itermap = {
            'count':len(filelist), 'subdircount':len(subdirlist),
            '_files': fileentlist,
            '_metadata': list(dir.metadata.items()),
        }
        dirents.append(ChainMap(itermap, dir.submap))

    itermap = { '_dirs':dirents }
    
    filename = os.path.join(DESTDIR, 'Master-Index.xml')
    tempname = os.path.join(DESTDIR, '__temp')
    writer = SafeWriter(tempname, filename)
    template.stream(itermap).dump(writer.stream())
    writer.resolve()

def generate_output(dirmap, jenv):
    """Write out all the index files.
    """
    if not os.path.exists(DESTDIR):
        os.mkdir(DESTDIR)
        
    dirlist = list(dirmap.values())
    for dir in dirlist:
        dirname = os.path.join(DESTDIR, dir.dir)
        os.makedirs(dirname, exist_ok=True)

    if opts.verbose:
        print('Generating output...')

    generate_output_dirlist(dirmap, jenv)
    generate_output_dirmap(dirmap, jenv)
    generate_output_datelist(dirmap, jenv)
    generate_output_indexes(dirmap)
    generate_output_xml(dirmap, jenv=jenv)

def generate_rss(dirmap, changedate, jenv):
    """Write out the archive.rss file.
    This will be the most recent two months' worth of files,
    excluding Master-Index, ls-lR, and files in /unprocessed.
    The changedate should be the timestamp on Master-Index.
    """
    excludeset = set([ 'Master-Index', 'ls-lR' ])
    intlen = 62*24*60*60

    # Create a list of all files sorted by date, newest to oldest.
    
    filelist = []
    for dir in dirmap.values():
        for file in dir.files.values():
            if file.name in excludeset:
                continue
            if file.path.startswith('if-archive/unprocessed/'):
                continue
            if file.parentdir.dir.endswith('/old'):
                continue
            if file.getkey('islink'):
                continue
            dateval = file.getkey('date')
            if dateval and int(dateval) + intlen >= curdate:
                filelist.append(file)

    # Same sorting criteria as in generate_output_datelist().
    filelist.sort(key=lambda file: (-int(file.getkey('date')), file.name.lower(), file.path.lower()))

    template = jenv.get_template('rss.xml')
    
    fileentlist = [ ChainMap({}, file.submap) for file in filelist ]
    
    itermap = { '_files':fileentlist, 'curdate':curdate, 'changedate':changedate }

    filename = os.path.join(DESTDIR, 'archive.rss')
    tempname = os.path.join(DESTDIR, '__temp')
    writer = SafeWriter(tempname, filename)
    template.stream(itermap).dump(writer.stream())
    writer.resolve()

    
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
            for key, valls in file.metadata.items():
                for val in valls:
                    writer.stream().write('%s: %s\n' % (key, val,))
            writer.resolve()

            writer = SafeWriter(tempname, filebase+'.json')
            json.dump(file.metadata, writer.stream(), indent=1)
            writer.stream().write('\n')
            writer.resolve()
            
            writer = SafeWriter(tempname, filebase+'.xml')
            writer.stream().write('<?xml version="1.0"?>\n')
            writer.stream().write('<metadata>\n')
            for key, valls in file.metadata.items():
                writer.stream().write(' <item><key>%s</key>\n' % (escape_html_string(key),))
                for val in valls:
                    writer.stream().write('  <value>%s</value>\n' % (escape_html_string(val),))
                writer.stream().write(' </item>\n')
            writer.stream().write('</metadata>\n')
            writer.resolve()

# Begin work!
# We only do this if we're the executing script. If this is just an imported
# module, we do no work. (This lets the test script "import ifmap" for unit
# tests.)

if __name__ == '__main__':
    (opts, args) = popt.parse_args()

    if not opts.libdir:
        raise Exception('--src argument required')

    if not opts.curdate:
        curdate = int(time.time())
    else:
        tup = datetime.datetime.fromisoformat(opts.curdate)
        curdate = int(tup.timestamp())

    hasher = FileHasher()
    noindexlist = NoIndexEntry()
    nounboxlinklist = DirList('no-unbox-link')
    mapskippatternlist = DirList('map-skip-patterns')
    # The skip-patterns are regexes, not pathnames.
    
    Template.addfilter('html', escape_html_string)
    Template.addfilter('slashwbr', slash_add_wbr)
    Template.addfilter('wikipage', escape_wikipage)
    Template.addfilter('url', escape_url_string)
    Template.addfilter('isodate', isodate)
    Template.addfilter('indexuri', indexuri_dirname)
    Template.addfilter('plural_s', pluralize_s)
    Template.addfilter('plural_ies', pluralize_ies)

    def jenvfilter(key, func):
        class JenvFilterExt(Extension):
            def __init__(self, env):
                env.filters[key] = func
        return JenvFilterExt
    
    jenv = Environment(
        loader = FileSystemLoader(opts.libdir),
        extensions = [
            jenvfilter('isodate', isodate),
            jenvfilter('pluralize', pluralize),
        ],
        autoescape = select_autoescape(),
        keep_trailing_newline = True,
    )
    
    convertermeta = markdown.Markdown(extensions = ['meta'])
    
    if not opts.treedir:
        DESTDIR = os.path.join('.', opts.destdir)
    else:
        DESTDIR = os.path.join(opts.treedir, opts.destdir)
        
    archtree = construct_archtree(opts.indexpath, opts.treedir)

    stat = os.stat(opts.indexpath)
    indexmtime = int(stat.st_mtime)
    
    check_missing_files(archtree.dirmap)
    
    generate_output(archtree.dirmap, jenv=jenv)
    generate_metadata(archtree.dirmap)
    
    generate_rss(archtree.dirmap, indexmtime, jenv=jenv)
    
