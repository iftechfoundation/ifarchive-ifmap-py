#!/usr/bin/env python3

# To run:
#   python3 tests.py

# This used to have a lot of tests for the Template and ParamFile classes.
# But we've gotten rid of those. So this is pretty vestigial.

import unittest

from ifmap import is_string_nonwhite

class TestEscapeFunctions(unittest.TestCase):

    def test_is_string_nonwhite(self):
        self.assertIs(is_string_nonwhite(''), False)
        self.assertIs(is_string_nonwhite('   '), False)
        self.assertIs(is_string_nonwhite('\n  \t  \n'), False)
        self.assertIs(is_string_nonwhite('x'), True)
        self.assertIs(is_string_nonwhite('x      \n'), True)
        self.assertIs(is_string_nonwhite('\n      x'), True)
        
        
if __name__ == '__main__':
    unittest.main()
    
