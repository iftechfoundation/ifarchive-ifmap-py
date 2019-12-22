#!/usr/bin/env python3

# To run:
#   python3 tests.py

import unittest
import io

from ifmap import escape_html_string, escape_url_string
from ifmap import is_string_nonwhite
from ifmap import Template, ParamFile

class TestEscapeFunctions(unittest.TestCase):

    def setUp(self):
        # This sets up global Template state, but it's harmless if we
        # do it more than once.
        Template.addfilter('html', escape_html_string)
        Template.addfilter('url', escape_url_string)
        Template.addfilter('upper', lambda val:val.upper())
        Template.addfilter('lower', lambda val:val.lower())
        
    def test_escape_html_string(self):
        self.assertEqual(escape_html_string('foo'), 'foo')
        self.assertEqual(escape_html_string('foo<i>&'), 'foo&lt;i&gt;&amp;')
        self.assertEqual(escape_html_string('w x\ny\tz'), 'w x\ny\tz')
        self.assertEqual(escape_html_string('x\x01y'), 'x&#x1;y')
        self.assertEqual(escape_html_string('© αβγδε “”'), '&#xA9; &#x3B1;&#x3B2;&#x3B3;&#x3B4;&#x3B5; &#x201C;&#x201D;')

    def test_escape_url_string(self):
        self.assertEqual(escape_url_string('foo'), 'foo')
        self.assertEqual(escape_url_string('http://foo/bar?x&y=z%'), 'http://foo/bar%3Fx%26y%3Dz%25')

    def test_is_string_nonwhite(self):
        self.assertIs(is_string_nonwhite(''), False)
        self.assertIs(is_string_nonwhite('   '), False)
        self.assertIs(is_string_nonwhite('\n  \t  \n'), False)
        self.assertIs(is_string_nonwhite('x'), True)
        self.assertIs(is_string_nonwhite('x      \n'), True)
        self.assertIs(is_string_nonwhite('\n      x'), True)
        
class TestSubstitutions(unittest.TestCase):

    def substitute(self, body, map):
        fl = io.StringIO()
        Template.substitute(body, map, outfl=fl)
        res = fl.getvalue()
        fl.close()
        return res

    def test_basic(self):
        self.assertEqual(self.substitute('foo{}bar', {}), 'foobar')
        self.assertEqual(self.substitute('foo', {}), 'foo')
        self.assertEqual(self.substitute('One\nαβγδε\n<&>“”\n', {}), 'One\nαβγδε\n<&>“”\n')
        self.assertEqual(self.substitute('escape {{}!', {}), 'escape {!')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':'xxx' }), 'foo=xxx')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':'αβγδε' }), 'foo=αβγδε')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':'' }), 'foo=')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':123 }), 'foo=123')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':True }), 'foo=True')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':False }), 'foo=False')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':(lambda outfl: outfl.write('xyzzy')) }), 'foo=xyzzy')
        
    def test_conditionals(self):
        map = {
            'str': 'string',
            'empty': '',
            'zero': 0,
            'int': 987,
            'true': True,
            'false': False,
            'func': (lambda outfl: outfl.write('function')),
        }
        self.assertEqual(self.substitute('{str} {int} {func}', map), 'string 987 function')
        
        self.assertEqual(self.substitute('{?str}yes{/}', map), 'yes')
        self.assertEqual(self.substitute('{?str}yes{:}no{/}', map), 'yes')
        self.assertEqual(self.substitute('{?str}yes-1{/} {?missing}yes-2{/}.', map), 'yes-1 .')

        self.assertEqual(self.substitute('{?int}{str}{:}{zero}{/}', map), 'string')
        self.assertEqual(self.substitute('{?empty}{empty}{:}is-empty{/}', map), 'is-empty')
        self.assertEqual(self.substitute('{?missing}{missing}{:}is-missing{/}', map), 'is-missing')

        self.assertEqual(self.substitute('{?empty}yes{:}no{/}', map), 'no')
        self.assertEqual(self.substitute('{?missing}yes{:}no{/}', map), 'no')
        self.assertEqual(self.substitute('{?int}yes{:}no{/}', map), 'yes')
        self.assertEqual(self.substitute('{?zero}yes{:}no{/}', map), 'no')
        self.assertEqual(self.substitute('{?true}yes{:}no{/}', map), 'yes')
        self.assertEqual(self.substitute('{?false}yes{:}no{/}', map), 'no')
        
        self.assertEqual(self.substitute('{?flag1}yes-1/{?flag2}yes-2{:}no-2{/}{:}no-1/{?flag2}yes-2{:}no-2{/}{/}.', {}), 'no-1/no-2.')
        self.assertEqual(self.substitute('{?flag1}yes-1/{?flag2}yes-2{:}no-2{/}{:}no-1/{?flag2}yes-2{:}no-2{/}{/}.', { 'flag1':True }), 'yes-1/no-2.')
        self.assertEqual(self.substitute('{?flag1}yes-1/{?flag2}yes-2{:}no-2{/}{:}no-1/{?flag2}yes-2{:}no-2{/}{/}.', { 'flag2':True }), 'no-1/yes-2.')
        self.assertEqual(self.substitute('{?flag1}yes-1/{?flag2}yes-2{:}no-2{/}{:}no-1/{?flag2}yes-2{:}no-2{/}{/}.', { 'flag1':True, 'flag2':True }), 'yes-1/yes-2.')

    def test_filters(self):
        self.assertEqual(self.substitute('foo={bar}', { 'bar':'xxx' }), 'foo=xxx')
        self.assertEqual(self.substitute('foo={bar|upper}', { 'bar':'xxx' }), 'foo=XXX')
        self.assertEqual(self.substitute('foo={bar|lower}', { 'bar':'XXX' }), 'foo=xxx')
        self.assertEqual(self.substitute('foo={bar|upper}, {bar|lower}', { 'bar':'Xy' }), 'foo=XY, xy')
        self.assertEqual(self.substitute('foo={bar|lower}', { 'bar':'XXX' }), 'foo=xxx')
        self.assertEqual(self.substitute('foo={bar|upper|lower}', { 'bar':'XyZw' }), 'foo=xyzw')
        self.assertEqual(self.substitute('foo={bar|upper}', { 'bar':123 }), 'foo=123')
        self.assertEqual(self.substitute('foo={bar|html|upper}', { 'bar':'x&y' }), 'foo=X&AMP;Y')
        self.assertEqual(self.substitute('foo={bar|upper|html}', { 'bar':'x&y' }), 'foo=X&amp;Y')

        def subfunc(outfl):
            Template.substitute('bar={baz|upper}', { 'baz':'text' }, outfl=outfl)
        self.assertEqual(self.substitute('foo={bar}', { 'bar':subfunc }), 'foo=bar=TEXT')

class TestParamFile(unittest.TestCase):
    
    def test_simple_paramfile(self):
        params = ParamFile('testdata/simple-params')
        self.assertEqual(params.body, 'This space is a thing.\n')
        self.assertEqual(len(params.map), 2)
        self.assertEqual(params.map['Main-Template'], 'main.html')
        self.assertEqual(params.map['Top-Level-Template'], 'αβγδε.html')

    
    def test_extra_paramfile(self):
        params = ParamFile('testdata/extra-params')
        self.assertEqual(params.body, '    Okay, this is the body.\nαβγδε In Greek.\n\nAnother.\n')
        self.assertEqual(len(params.map), 3)
        self.assertEqual(params.map['foo'], 'Line foo')
        self.assertEqual(params.map['bar'], 'Line bar\nmore bar\nwith stuff')
        self.assertEqual(params.map['baz'], 'BAZ')
        
if __name__ == '__main__':
    unittest.main()
    
