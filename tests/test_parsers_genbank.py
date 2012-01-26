"""
Tests for the mutalyzer.parsers.genbank module.
"""


#import logging; logging.basicConfig()
from nose.tools import *

from mutalyzer.parsers import genbank


class TestMutator():
    """
    Test the mutator module.
    """
    def setUp(self):
        """
        Initialize test mutator module.
        """
        self.gb_parser = genbank.GBparser()

    def test_product_lists_mismatch(self):
        """
        Test finding mismatches in some product lists.
        """
        tests = [(['a b c d e', 'a b C D e', 'a b c d e'], (2, 1)),
                 (['a b c d e', 'a b C d e', 'a B c d e'], (1, 2)),
                 (['a c d a', 'a b a', 'a a', 'a'], (1, 1)),
                 ([''], (-1, -1)),
                 (['', ''], (-1, -1)),
                 (['a', 'a'], (-1, -1)),
                 (['a', 'b'], (0, 0)),
                 (['a b c', 'a b c'], (-1, -1)),
                 (['a b c d a b', 'a b'], (2, 2))]
        for test in tests:
            assert_equal(self.gb_parser._find_mismatch(test[0]), test[1])