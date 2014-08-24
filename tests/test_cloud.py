import unittest

from pumphouse import cloud
from mock import patch, Mock, MagicMock
from keystoneclient.v2_0 import client as keystone_client
import sqlalchemy as sqla

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


class IdentityTestCase(unittest.TestCase):

    def setUp(self):
        with patch.object(sqla, 'create_engine') as mock:
            fakeEngine = MagicMock()
            fakeEngine.execute.return_value =  [(None, "passw0rd")];
            fakeEngine.begin.return_value = fakeEngine


            mock.create_engine.return_value = fakeEngine
            self.identity = cloud.Identity(None)

            self.identity.engine = fakeEngine


    def testInit(self):
        self.assertIsInstance(self.identity, cloud.Identity)

    def testFetch(self):
        self.assertTrue(self.identity.fetch("user") == "passw0rd")

    def testUpdate(self):
        self.identity.update([ ("user", "passw0rd") ] )

#    def testPush(self):
#        self.identity.push()

    def testGetter(self):
        self.identity["user"]
        self.identity["user"]
        self.identity.push()
        len(self.identity)




#class CloudTestCase(unittest.TestCase):
#    def setUp(self):
#        self.nspace = cloud.Namespace(
#            username="user",
#            password="password",
#            tenant_name="tenant",
#            auth_url="auth",
#        )
#
#        self.identity = Mock()
#
#    @patch.object(keystone_client.Client, 'authenticate' )
#    def testInit(self, mock_path):
#        mock_path.authenticate.return_value = True
#        self.assertIsInstance(cloud.Cloud(self.nspace, self.identity), cloud.Cloud)

if __name__ == '__main__':
   unittest.main()
