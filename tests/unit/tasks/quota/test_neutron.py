from mock import Mock
import unittest

from pumphouse.tasks.quota import neutron


class TestNeutronQuota(unittest.TestCase):
    def setUp(self):
        self.tenant_id = Mock(name="tenant_id")
        self.tenant_info = {
            "id": self.tenant_id
        }
        self.quota_info = {
            "a": 1,
            "b": 2
        }
        self.cloud = Mock(name="cloud")


class TestRetrieveTenantQuota(TestNeutronQuota):
    def test_execute(self):
        task = neutron.RetrieveTenantQuota(self.cloud)
        quota = task.execute(self.tenant_id)

        show_quota = self.cloud.neutron.show_quota
        show_quota.assert_called_once_with(
            self.tenant_id
        )
        self.assertEqual(quota, show_quota.return_value)


class TestEnsureTenantQuota(TestNeutronQuota):
    def test_execute(self):
        task = neutron.EnsureTenantQuota(self.cloud)
        quota = task.execute(self.quota_info, self.tenant_info)

        update_quota = self.cloud.neutron.update_quota
        update_quota.assert_called_once_with(
            self.tenant_id,
            self.quota_info
        )
        self.assertEqual(quota, update_quota.return_value)
