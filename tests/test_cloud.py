import unittest

from pumphouse import cloud


class NamespaceTestCase(unittest.TestCase):
    def setUp(self):
        self.nspace = cloud.Namespace(
            username="user",
            password="password",
            tenant_name="tenant",
            auth_url="auth",
        )

    def test_init(self):
        self.assertEqual("user", self.nspace.username)
        self.assertEqual("password", self.nspace.password)
        self.assertEqual("tenant", self.nspace.tenant_name)
        self.assertEqual("auth", self.nspace.auth_url)

    def test_restrict_by_tenant(self):
        n = self.nspace.restrict(tenant_name="rst_tenant")
        self.assertEqual("user", n.username)
        self.assertEqual("password", n.password)
        self.assertEqual("rst_tenant", n.tenant_name)
        self.assertEqual("auth", n.auth_url)

    def test_to_dict(self):
        dict_ns = self.nspace.to_dict()
        self.assertEqual("user", dict_ns["username"])
        self.assertEqual("password", dict_ns["password"])
        self.assertEqual("tenant", dict_ns["tenant_name"])
        self.assertEqual("auth", dict_ns["auth_url"])
