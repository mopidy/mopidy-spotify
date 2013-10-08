import unittest

from mopidy_spotify import Extension, frontend as frontend_lib


class ExtensionTest(unittest.TestCase):

    def test_get_default_config(self):
        ext = Extension()

        config = ext.get_default_config()

        self.assertIn('[spotify]', config)
        self.assertIn('enabled = true', config)

    def test_get_config_schema(self):
        ext = Extension()

        schema = ext.get_config_schema()

        self.assertIn('username', schema)
        self.assertIn('password', schema)
        self.assertIn('bitrate', schema)
        self.assertIn('timeout', schema)
        self.assertIn('cache_dir', schema)

    # TODO Write more tests
