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

    def test_add_already_registerd_fail(self):
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

    def test_select_not_found_fail(self):
        with self.assertRaises(excs.FuncNotFoundError) as cm:
            self.plugin.select("unknown")
        err = cm.exception
        self.assertEqual("test", err.target)
        self.assertEqual("unknown", err.name)


class RegistryTestCase(unittest.TestCase):
    def setUp(self):
        self.registry = plugin.Registry()

    def test_register_and_get(self):
        plg = self.registry.register("plg")
        plg_get = self.registry.get("plg")
        self.assertIs(plg_get, plg)

    def test_register_already_register_fail(self):
        plg = self.registry.register("plg")
        with self.assertRaises(excs.PluginAlreadyRegisterError) as cm:
            self.registry.register("plg")
        self.assertEqual("plg", cm.exception.target)

    def test_get_not_found_fail(self):
        with self.assertRaises(excs.PluginNotFoundError) as cm:
            self.registry.get("plg")
        self.assertEqual("plg", cm.exception.target)
