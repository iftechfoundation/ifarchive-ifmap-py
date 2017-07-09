#!/usr/bin/env python3

# To run:
#   python3 tests.py

import unittest
import io

from ifmap import escape_html_string, escape_htmldesc_string, escape_url_string
from ifmap import is_string_nonwhite
from ifmap import Template

class TestEscapeFunctions(unittest.TestCase):
    
    def test_escape_html_string(self):
        self.assertEqual(escape_html_string('foo'), 'foo')
        self.assertEqual(escape_html_string('foo<i>&'), 'foo&lt;i&gt;&amp;')
        self.assertEqual(escape_html_string('w x\ny\tz'), 'w x\ny\tz')
        self.assertEqual(escape_html_string('x\x01y'), 'x&#x1;y')
        self.assertEqual(escape_html_string('© αβγδε “”'), '&#xA9; &#x3B1;&#x3B2;&#x3B3;&#x3B4;&#x3B5; &#x201C;&#x201D;')

    def test_escape_htmldesc_string(self):
        self.assertEqual(escape_htmldesc_string('foo'), 'foo')
        self.assertEqual(escape_htmldesc_string('foo<i>'), 'foo&lt;i&gt;')
        self.assertEqual(escape_htmldesc_string('w x\ny\tz'), 'w x\ny\tz')
        self.assertEqual(escape_htmldesc_string('<http://foo>'), '<a href="http://foo">http://foo</a>')
        self.assertEqual(escape_htmldesc_string('<http://foo'), '&lt;http://foo')
        self.assertEqual(escape_htmldesc_string('<http://foo> <https://bar/b> <x>'), '<a href="http://foo">http://foo</a> <a href="https://bar/b">https://bar/b</a> &lt;x&gt;')
        self.assertEqual(escape_htmldesc_string('<http://foo?bar&baz>'), '<a href="http://foo?bar&amp;baz">http://foo?bar&amp;baz</a>')
        ### escape_htmldesc_string currently does not escape & or &...;
        ### sequences. Add tests when it does.

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
        self.assertEqual(self.substitute('foo', {}), 'foo')
        self.assertEqual(self.substitute('One\nαβγδε\n<&>“”\n', {}), 'One\nαβγδε\n<&>“”\n')
        self.assertEqual(self.substitute('escape {{}!', {}), 'escape {!')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':'xxx' }), 'foo=xxx')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':123 }), 'foo=123')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':True }), 'foo=True')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':False }), 'foo=False')
        self.assertEqual(self.substitute('foo={bar}', { 'bar':'' }), 'foo=')
    
if __name__ == '__main__':
    unittest.main()
    
