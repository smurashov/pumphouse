import unittest
from mock import Mock, patch, call

from pumphouse import task
from pumphouse.tasks import tenant
from pumphouse.exceptions import keystone_excs


class TenantTestCase(unittest.TestCase):
    def setUp(self):
        self.dummy_id = '123'
        self.tenant_info = {
            'name': 'dummy',
            'description': 'dummydummy',
            'enabled': True
        }

        self.tenant = Mock()
        self.tenant.to_dict.return_value = dict(self.tenant_info,
                                                id=self.dummy_id)

        self.context = Mock()
        self.context.store = {}

        self.cloud = Mock()
        self.cloud.keystone.tenants.get.return_value = self.tenant
        self.cloud.keystone.tenants.find.return_value = self.tenant
        self.cloud.keystone.tenants.create.return_value = self.tenant


class TestRetrieveTenant(TenantTestCase):
    def test_retrieve_is_task(self):
        retrieve_tenant = tenant.RetrieveTenant(self.cloud)
        self.assertIsInstance(retrieve_tenant, task.BaseCloudTask)

    def test_retrieve(self):
        retrieve_tenant = tenant.RetrieveTenant(self.cloud)
        tenant_info = retrieve_tenant.execute(self.dummy_id)
        self.cloud.keystone.tenants.get.assert_called_once_with(self.dummy_id)
        self.assertEqual("123", tenant_info["id"])
        self.assertEqual("dummy", tenant_info["name"])
        self.assertEqual("dummydummy", tenant_info["description"])
        self.assertEqual(True, tenant_info["enabled"])


class TestEnsureTenant(TenantTestCase):
    def test_execute(self):
        ensure_tenant = tenant.EnsureTenant(self.cloud)
        ensure_tenant.execute(self.tenant_info)

        self.assertIsInstance(ensure_tenant, task.BaseCloudTask)
        self.cloud.keystone.tenants.find.assert_called_once_with(
            name=self.tenant_info["name"]
        )
        self.assertFalse(self.cloud.keystone.tenants.create.called)

    def test_execute_not_found(self):
        self.cloud.keystone.tenants.find.side_effect = keystone_excs.NotFound

        ensure_tenant = tenant.EnsureTenant(self.cloud)
        ensure_tenant.execute(self.tenant_info)

        self.cloud.keystone.tenants.create.assert_called_once_with(
            "dummy",
            description="dummydummy",
            enabled=True
        )


class TestMigrateTenant(TenantTestCase):

    @patch.object(tenant, "RetrieveTenant")
    @patch.object(tenant, "EnsureTenant")
    @patch.object(tenant, "AddTenantAdmin")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_tenant(self, mock_flow,
                            mock_add_tenant_admin,
                            mock_ensure_tenant,
                            mock_retrieve_tenant):
        flow = tenant.migrate_tenant(
            self.context,
            self.dummy_id,
        )
        mock_flow.assert_called_once_with("migrate-tenant-%s" % self.dummy_id)
        self.assertEqual(1, mock_retrieve_tenant.call_count)
        self.assertEqual(1, mock_ensure_tenant.call_count)
        self.assertEqual(1, mock_add_tenant_admin.call_count)

        self.assertEqual(
            mock_flow().add.call_args,
            call(
                mock_retrieve_tenant(),
                mock_ensure_tenant(),
                mock_add_tenant_admin(),
            )
        )
        self.assertEqual(
            self.context.store,
            {"tenant-%s-retrieve" % self.dummy_id: self.dummy_id}
        )


if __name__ == '__main__':
    unittest.main()
