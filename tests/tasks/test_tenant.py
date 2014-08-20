import unittest
from mock import Mock, patch

from pumphouse.tasks import tenant
from pumphouse.exceptions import keystone_excs
from taskflow.patterns import linear_flow


class TenantTestCase(unittest.TestCase):
    def setUp(self):
        self.dummy_id = '123'
        self.tenant_info = {
            'name': 'dummy',
            'description': 'dummydummy',
            'enabled': True
        }

        self.tenant = Mock()
        self.tenant.to_dict.return_value = {}

        self.dst = Mock()

        self.cloud = Mock()
        self.cloud.keystone.tenants.get.return_value = self.dummy_id
        self.cloud.keystone.tenants.find.return_value = self.tenant
        self.cloud.keystone.tenants.create.return_value = self.tenant


class TestRetrieveTenant(TenantTestCase):
    def test_retrieve(self):
        tenant.RetrieveTenant(self.cloud).retrieve(self.dummy_id)
        # Assures cloud.keystone.tenants.get method is called with
        # the parameter supplied
        self.cloud.keystone.tenants.get.assert_called_with(self.dummy_id)


class TestEnsureTenant(TenantTestCase):
    def test_execute(self):
        ensure_tenant = tenant.EnsureTenant(self.cloud)

        # Assures that no cloud.keystone.tenants.create method is not called
        # if cloud.keystone.tenants.find does not raise Not Found exception
        # i.e. tenant is found by its name
        ensure_tenant.execute(self.tenant_info)
        self.assertFalse(self.cloud.keystone.tenants.create.called)

    def test_execute_not_found(self):
        ensure_tenant = tenant.EnsureTenant(self.cloud)

        # In case if Not Found exception is raised by ...find call
        # assures that cloud.keystone.tenants.create is called
        self.cloud.keystone.tenants.find.side_effect = keystone_excs.NotFound
        ensure_tenant.execute(self.tenant_info)
        self.cloud.keystone.tenants.create.assert_called_once_with(
            "dummy", description="dummydummy", enabled=True)


class TestMigrateTenant(TenantTestCase):

    @patch.object(linear_flow.Flow, 'add')
    def test_migrate_tenant(self, mock_flow):
        mock_flow.return_value = self.dummy_id
        store = {}

        (flow, store) = tenant.migrate_tenant(
            self.tenant,
            self.dst,
            store,
            self.dummy_id)
        # Assures linear_flow.Flow().add is called
        self.assertTrue(mock_flow.called)

        # Assures that new flow is added to store after execution
        self.assertNotEqual({}, store)


if __name__ == '__main__':
    unittest.main()
