from __future__ import unicode_literals

import unittest

from mopidy_local_zodb import Extension


class ExtensionTest(unittest.TestCase):

    def test_get_default_config(self):
        ext = Extension()

        config = ext.get_default_config()

        self.assertIn('[local-zodb]', config)
        self.assertIn('enabled = true', config)

    # TODO Write more tests
