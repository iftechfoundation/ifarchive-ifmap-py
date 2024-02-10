#!/usr/bin/env python3

# To run:
#   python3 tests.py

# This used to have a lot of tests for the Template and ParamFile classes.
# But we've gotten rid of those. So this is pretty vestigial.

import unittest

from ifmap import is_string_nonwhite
from ifmap import escape_html_string

class TestEscapeFunctions(unittest.TestCase):

    def test_escape_html_string(self):
        self.assertEqual(escape_html_string('foo'), 'foo')
        self.assertEqual(escape_html_string('foo<i>&'), 'foo&lt;i&gt;&amp;')
        self.assertEqual(escape_html_string('w x\ny\tz'), 'w x\ny\tz')
        self.assertEqual(escape_html_string('x\x01y'), 'x&#x1;y')
        self.assertEqual(escape_html_string('© αβγδε “”'), '&#xA9; &#x3B1;&#x3B2;&#x3B3;&#x3B4;&#x3B5; &#x201C;&#x201D;')

    def test_is_string_nonwhite(self):
        self.assertIs(is_string_nonwhite(''), False)
        self.assertIs(is_string_nonwhite('   '), False)
        self.assertIs(is_string_nonwhite('\n  \t  \n'), False)
        self.assertIs(is_string_nonwhite('x'), True)
        self.assertIs(is_string_nonwhite('x      \n'), True)
        self.assertIs(is_string_nonwhite('\n      x'), True)
        
        
if __name__ == '__main__':
    unittest.main()
    
