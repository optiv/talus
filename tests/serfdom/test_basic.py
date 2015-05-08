#!/usr/bin/env python

import os
import sys
import random
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import serfdom

class BasicSerfdomTest(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_simple(self):
        pass

if __name__ == "__main__":
    unittest.main()
