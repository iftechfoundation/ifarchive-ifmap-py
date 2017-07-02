#!/usr/bin/env python3

import sys
import re
import os.path
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
    return val.replace('/', 'X')

class Directory:
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
        
        self.files = {}

    def __repr__(self):
        return '<Directory %s>' % (self.dir,)

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
    filemap = {}

    dir = Directory(ROOTNAME)
    dirmap[dir.dir] = dir

    if indexpath:
        dirname_pattern = re.compile('^%s.*:$' % (re.escape(ROOTNAME),))
        
        dir = None
        file = None
        filestr = None
        inheader = True
        headerpara = True
        headerstr = None
        
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
                        if filestr is not None:
                            file.putkey('desc', filestr)
                            file.putkey('hasdesc', is_string_nonwhite(filestr))
                        ### filestrraw?
                        filemap[file.getkey('rawname')] = file
                        file = None

                    dirname = dir.dir
                    if opts.verbose:
                        print('Completing %s...' % (dirname,))
                    dirmap[dirname] = dir

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
                        print('Completing %s...' % (dirname,))
                    dir = Directory(dirname)
                    
                    filestr = None
                    inheader = True
                    headerpara = True
                    headerstr = None

                continue

            if dir is None:
                continue

    return dirmap
    
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

dirmap = parse_master_index(opts.indexpath, opts.treedir)
dir = dirmap[ROOTNAME]
dir.submap['hasdesc'] = True
dir.submap['header'] = toplevel_body


