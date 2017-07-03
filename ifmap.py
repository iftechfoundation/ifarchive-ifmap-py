#!/usr/bin/env python3

### TODO:
### move dirmap insertion to the top
### name, rawname are bad labels. swap around.
### correct escaping of everything
### all the xml stuff
### The N^2 loop in parse?

import sys
import re
import os
import os.path
import time
from collections import ChainMap
import optparse

ROOTNAME = 'if-archive'

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

class TemplateTag:
    """Data element used inside a Template.
    """
    def __init__(self, val, type=None):
        self.value = val
        self.type = type
    def __repr__(self):
        return '<TemplateTag %s:%r>' % (self.type, self.value)
        
class Template:
    """Template: A basic template-substitution system.

    You normally don't create Template objects. Instead, call
    Template.substitute(body, map). This will create a Template
    object if needed (caching known ones for speed) and then perform
    the substitution.

    The template language supports these tags:

    {foo}: Substitute the value of map['foo'].
    {?foo}if-yes{/}: If map['foo'] exists, substitute the if-yes part.
    {?foo}if-yes{:}if-no{/}: If map['foo'] exists, substitute the if-yes
        part; otherwise the if-no part.

    If-then tags can be nested. {foo} is an error if the foo tag is
    missing or its value is None.

    The {?foo} test treats missing tags, None, and False as "no" results.
    Zero and the empty string are treated as "yes", which is not the
    usual Python convention, but our needs are specialized.
    """
    
    tag_pattern = re.compile('[{]([^}]*)[}]')

    cache = {}
    
    @staticmethod
    def substitute(body, map, rock=None, outfl=sys.stdout):
        template = Template.cache.get(body)
        if template is None:
            template = Template(body)
            Template.cache[body] = template
        template.subst(map, rock, outfl)
    
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
                tag = TemplateTag(val, 'var')
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
                ls.append('{%s}' % (tag.value,))
            else:
                ls.append('{???}')
        return '<Template %r>' % (''.join(ls),)

    def subst(self, map, rock=None, outfl=sys.stdout):
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
                    flag = (val is not None) and (val is not False)
                    activelist.append(flag)
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
                    val(outfl, rock)
                elif type(val) in (str, int, float, bool):
                    outfl.write(str(val))
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
    
def expandtabs(val, colwidth=8):
    """Expand tabs in a string, using a given tab column width.
    (This is fast if val contains no tabs. It's not super-efficient
    if val contains a lot of tabs, but in fact our files contain
    very few tabs, so that's okay.)
    """
    start = 0
    while True:
        pos = val.find('\t', start)
        if pos < 0:
            return val
        spaces = 8 - (pos & 7)
        val = val[0:pos] + (' '*spaces) + val[pos+1:]

def xify_dirname(val):
    """Convert a directory name to an X-string, as used in the index.html
    filenames. The "if-archive/games" directory is mapped to
    "if-archiveXgames", for example.
    We acknowledge that this is ugly and stupid.
    """
    return val.replace('/', 'X')

def bracket_count(val):
    """Check the running bracket balance of a string. This does not
    distinguish between square brackets and parentheses. I can't remember
    why we need this.
    """
    count = 0
    for ch in val:
        if ch == '[' or ch == '(':
            count += 1
        if ch == ']' or ch == ')':
            count -= 1
    return count
    
def append_string(val, val2):
    if not val2:
        return val
    if not val:
        return val2
    return val + val2

def escape_string(val, forxml=False):
    return val ###

def escape_url_string(val):
    return val ###

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
    def __init__(self, dirname):
        self.dir = dirname
        self.submap = {}

        self.putkey('dir', dirname)
        self.putkey('xdir', xify_dirname(dirname))

        pos = dirname.rfind('/')
        if pos >= 0:
            parentdirname = dirname[0:pos]
            self.putkey('parentdir', parentdirname)
            self.putkey('xparentdir', xify_dirname(parentdirname))

        ### add_dir_links?
        self.files = {}
        self.subdirs = {}

    def __repr__(self):
        return '<Directory %s>' % (self.dir,)

    def getkey(self, key, default=None):
        return self.submap.get(key)
    
    def putkey(self, key, val):
        self.submap[key] = val

class File:
    """File: one file in the big directory map.
    (There is no global file list. You have to look at dir.files for each
    directory in dirmap.)
    """
    def __init__(self, filename, parentdir):
        self.submap = {}
        self.parentdir = parentdir
        parentdir.files[filename] = self

        self.rawname = filename
        self.putkey('rawname', filename)
        self.putkey('name', escape_string(filename))
        self.putkey('nameurl', escape_url_string(filename))
        ### namexml

        self.putkey('dir', parentdir.dir)

    def __repr__(self):
        return '<File %s>' % (self.rawname,)

    def complete(self, filestr):
        if filestr is not None:
            self.putkey('desc', filestr)
            self.putkey('hasdesc', is_string_nonwhite(filestr))
        ### filestrraw?
        
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

    dir = Directory(ROOTNAME)
    dirmap[dir.dir] = dir

    if indexpath:
        dirname_pattern = re.compile('^%s.*:$' % (re.escape(ROOTNAME),))
        dashline_pattern = re.compile('^[ ]*[-+=#*]+[ -+=#*]*$')
        indent_pattern = re.compile('^([ ]*)(.*)$')
        
        dir = None
        file = None
        filestr = None
        inheader = True
        headerpara = True
        headerstr = None
        brackets = 0
        
        infl = open(indexpath, encoding='utf-8')

        done = False
        while not done:
            ln = infl.readline()
            if not ln:
                done = True
                ln = None
            else:
                ln = ln.rstrip()
                ln = expandtabs(ln)

            if done or dirname_pattern.match(ln):
                # End of a directory block or end of file.
                # Finish constructing the dir entry.

                if dir:
                    if file:
                        # Also have to finish constructing the file entry.
                        file.complete(filestr)
                        file = None

                    dirname = dir.dir
                    if opts.verbose:
                        print('Finishing %s...' % (dirname,))
                    dirmap[dirname] = dir  ### move to constructor?

                    if headerstr is not None:
                        dir.putkey('header', headerstr)
                        dir.putkey('hasdesc', is_string_nonwhite(headerstr))
                        headerstr = None
                    ### headerstrraw?
                    dir = None

                if not done:
                    # Beginning of a directory block.
                    dirname = ln[0:-1]  # delete trailing colon
                    if opts.verbose:
                        print('Starting  %s...' % (dirname,))
                    dir = Directory(dirname)
                    
                    filestr = None
                    inheader = True
                    headerpara = True
                    headerstr = None

                continue

            # We can't do any work outside of a directory block.
            if dir is None:
                continue

            # Skip any line which is entirely dashes (or dash-like
            # characters). But we don't skip blank lines this way.
            if dashline_pattern.match(ln):
                continue

            match = indent_pattern.match(ln)
            indent = len(match.group(1))
            bx = match.group(2)

            if inheader:
                # The header ends when we find the line
                #       "Index   this file"
                # (Spacing and capitalization of the "this file" part
                # may vary.)
                if bx.startswith('Index'):
                    val = bx[5:].strip().lower()
                    if val.startswith('this file'):
                        inheader = False
                        continue

                # Further header lines become part of headerstr.
                if len(bx):
                    headerstr = append_string(headerstr, escape_string(bx, False))
                    headerstr = append_string(headerstr, '\n')
                    headerpara = False
                    ### headerstrraw
                else:
                    if not headerpara:
                        headerstr = append_string(headerstr, '<p>\n');
                        headerpara = True
                    ### headerstrraw
                
                continue

            if indent == 0 and bx:
                # Start of a new file block.

                if file:
                    # Finish constructing the file in progress.
                    file.complete(filestr)
                    file = None

                pos = bx.find(' ')
                if pos >= 0:
                    filename = bx[0:pos]
                    bx = bx[pos:]
                    match = indent_pattern.match(bx)
                    firstindent = pos + len(match.group(1))
                    bx = match.group(2)
                    brackets = bracket_count(bx)
                    filestr = escape_string(bx, False)
                    filestr = append_string(filestr, '\n')
                    ### filestrraw
                else:
                    filename = bx
                    bx = ''
                    firstindent = -1
                    filestr = None
                    ### filestrraw
                    
                file = File(filename, dir)

            else:
                # Continuing a file block.
                if bx:
                    if firstindent < 0:
                        firstindent = indent
                        brackets = 0
                    if (firstindent != indent) and (brackets == 0):
                        filestr = append_string(filestr, '<br>&nbsp;&nbsp;')
                        ### filestrraw
                    filestr = append_string(filestr, escape_string(bx, False))
                    filestr = append_string(filestr, '\n')
                    ### filestrraw
                    brackets += bracket_count(bx)
                ### filestrraw

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
                print('Scanning  %s...' % (dirname,))
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
                            ### check_exclude
                            file = File(ent.name, dir)
                            file.putkey('desc', ' ')
                        file.putkey('islink', True)
                        file.putkey('islinkfile', True)
                        file.putkey('linkpath', linkname) ### canonicalize?
                        file.putkey('date', str(int(sta2.st_mtime)))
                        tmdat = time.localtime(sta2.st_mtime)
                        file.putkey('datestr', time.strftime('%d-%b-%Y', tmdat))
                    elif ent.is_dir(follow_symlinks=True):
                        targetname = os.path.normpath(os.path.join(dirname, linkname))
                        file = dir.files.get(ent.name)
                        if file is None:
                            file = File(ent.name, dir)
                            file.putkey('desc', 'Symlink to '+targetname) ### escape?
                        file.putkey('islink', True)
                        file.putkey('islinkdir', True)
                        file.putkey('linkdir', targetname)
                        file.putkey('xlinkdir', xify_dirname(targetname))

                    continue
                        
                if ent.is_file():
                    if ent.name == 'Index':
                        continue
                    file = dir.files.get(ent.name)
                    if file is None:
                        ### check_exclude
                        file = File(ent.name, dir)
                        file.putkey('desc', ' ')
                    file.putkey('filesize', str(sta.st_size))
                    file.putkey('date', str(int(sta.st_mtime)))
                    tmdat = time.localtime(sta.st_mtime)
                    file.putkey('datestr', time.strftime('%d-%b-%Y', tmdat))
                    ### md5
                    continue

                if ent.is_dir():
                    dir2 = dirmap.get(dirname2)
                    if dir2 is None:
                        dir2 = Directory(dirname2)
                        dirmap[dirname2] = dir2
                    file = dir.files.get(ent.name)
                    if file is not None:
                        file.putkey('linkdir', dirname2)
                        file.putkey('xlinkdir', xify_dirname(dirname2))
                    if parentlist and parentdir:
                        parentname = os.path.join(parentdir, ent.name)
                        parentfile = parentlist.get(parentname)
                        if parentfile is not None:
                            parentfile.putkey('linkdir', dirname2)
                            parentfile.putkey('xlinkdir', xify_dirname(dirname2))
                    scan_directory(dirname2, dir.files, ent.name)
                    continue
                            
            # End of internal scan_directory function.

        # Call the above function recursively.
        scan_directory(ROOTNAME)

    # Create the subdir list and count for each directory.
    for dir in dirmap.values():
        dir.putkey('count', str(len(dir.files)))
        
        # This is N^2, sorry.
        ### Probably a better way exists.
        for subname, subdir in dirmap.items():
            if subname.startswith(dir.dir):
                val = subname[len(dir.dir):]
                if val.startswith('/') and val.find('/', 1) < 0:
                    dir.subdirs[subname] = subdir

        dir.putkey('subdircount', str(len(dir.subdirs)))
        
    return dirmap

def check_missing_files(dirmap):
    """Go through dirmap and look for entries which were not found in
    the scan-directory phase. We know an entry was not found if we
    never read its date (file timestamp).
    """
    for dir in dirmap.values():
        for file in dir.files.values():
            if file.getkey('date') is None and file.getkey('xlinkdir') is None and file.getkey('islink') is None:
                sys.stderr.write('Index entry without file: %s/%s\n' % (dir.dir, file.rawname))

def parity_flip(map):
    val = map.get('parity')
    if val == 'Even':
        map['parity'] = 'Odd'
    else:
        map['parity'] = 'Even'

def generate_output_dirlist(dirmap):
    filename = plan.get('Dir-List-Template')
    dirlist_body = read_lib_file(filename, '<html><body>\n{_dirs}\n</body></html>\n')

    dirlist_entry = plan.get('Dir-List-Entry', '<li>{dir}')
    
    def dirlist_thunk(outfl, rock):
        dirlist = list(dirmap.values())
        dirlist.sort(key=lambda dir:dir.dir.lower())
        itermap = {}
        for dir in dirlist:
            parity_flip(itermap)
            Template.substitute(dirlist_entry, ChainMap(itermap, dir.submap), outfl=outfl)
            outfl.write('\n')
            
    itermap = { '_dirs':dirlist_thunk }

    filename = os.path.join(opts.destdir, 'dirlist.html')
    outfl = open(filename, 'w', encoding='utf-8')
    Template.substitute(dirlist_body, ChainMap(itermap, plan.map), outfl=outfl)
    outfl.close()
    
def generate_output_datelist(dirmap):
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

    filelist.sort(key=lambda file: -int(file.getkey('date')))

    filename = plan.get('Date-List-Template')
    datelist_body = read_lib_file(filename, '<html><body>\n{_files}\n</body></html>\n')

    datelist_entry = plan.get('Date-List-Entry', '<li>{name}')

    curtime = int(time.time())
    
    for (intkey, intlen, intname) in intervals:
        if intkey:
            filename = os.path.join(opts.destdir, 'date_%d.html' % (intkey,))
        else:
            filename = os.path.join(opts.destdir, 'date.html')

        def filelist_thunk(outfl, rock):
            itermap = {}
            for file in filelist:
                parity_flip(itermap)
                if intlen:
                    if int(file.getkey('date')) + intlen < curtime:
                        break
                Template.substitute(datelist_entry, ChainMap(itermap, file.submap), outfl=outfl)
                outfl.write('\n')
                
        itermap = { '_files':filelist_thunk }
        if intname:
            itermap['interval'] = intname
            
        outfl = open(filename, 'w', encoding='utf-8')
        Template.substitute(datelist_body, ChainMap(itermap, plan.map), outfl=outfl)
        outfl.close()
    

def generate_output(dirmap):
    if not os.path.exists(opts.destdir):
        os.mkdir(opts.destdir)

    generate_output_dirlist(dirmap)
    generate_output_datelist(dirmap)
        
    filename = plan.get('XML-Template')
    xmllist_body = read_lib_file(filename, '<xml>\n{_dirs}\n</xml>\n')



# Begin work!

(opts, args) = popt.parse_args()

if not opts.libdir:
    raise Exception('--src argument required')
if not opts.destdir:
    raise Exception('--dest argument required')

plan = ParamFile(os.path.join(opts.libdir, 'index'))

filename = plan.get('Top-Level-Template')
toplevel_body = read_lib_file(filename, 'Welcome to the archive.\n')

dirmap = parse_master_index(opts.indexpath, opts.treedir)
dir = dirmap[ROOTNAME]
dir.submap['hasdesc'] = True
dir.submap['header'] = toplevel_body

check_missing_files(dirmap)

generate_output(dirmap)
