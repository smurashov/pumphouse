import unittest

from pumphouse import exceptions as excs
from pumphouse import plugin


class PluginTestCase(unittest.TestCase):
    def setUp(self):
        self.plugin = plugin.Plugin("test")

    def test_add(self):
        impl = lambda x: x
        added = self.plugin.add("impl")(impl)
        self.assertIs(added, impl)
        self.assertIn("impl", self.plugin.implements)

    def test_add_already_registerd(self):
        self.plugin.add("impl")(lambda x: x)
        with self.assertRaises(excs.FuncAlreadyRegisterError) as cm:
            self.plugin.add("impl")(lambda x: x)
        err = cm.exception
        self.assertEqual("test", err.target)
        self.assertEqual("impl", err.name)

    def test_select(self):
        impl = lambda x: x
        self.plugin.add("impl")(impl)
        selected = self.plugin.select("impl")
        self.assertIs(selected, impl)

    def test_select_not_found(self):
        with self.assertRaises(excs.FuncNotFoundError) as cm:
            self.plugin.select("unknown")
        err = cm.exception
        self.assertEqual("test", err.target)
        self.assertEqual("unknown", err.name)
