from mock import Mock, patch
import unittest

from pumphouse.tasks.quota import base


class TestBaseQuota(unittest.TestCase):
    def setUp(self):
        self.tenant_id = Mock(name="tenant_id")
        self.cloud = Mock(name="cloud")
        self.tenant_info = {
            "id": self.tenant_id
        }
        self.quota_info = {
            "a": "1",
            "b": "2"
        }

    def assertRetrieveQuota(self, mock_called, info):
        mock_called.assert_called_once_with(self.tenant_id)
        self.assertEquals(info, mock_called.return_value._info)

    def assertEnsureQuota(self, mock_called, id, info):
        mock_called.assert_called_once_with(
            id,
            a="1",
            b="2"
        )
        self.assertEqual(info, mock_called.return_value._info)


class TestRetrieveTenantQuota(TestBaseQuota):
    @patch.object(base.RetrieveTenantQuota, "client")
    def test_execute(self, mock_client):
        retrieve_tenant_quota = base.RetrieveTenantQuota(self.cloud)
        self.assertRetrieveQuota(mock_client.quotas.get,
                                 retrieve_tenant_quota.execute(self.tenant_id))


class TestRetrieveDefaultQuota(TestBaseQuota):
    @patch.object(base.RetrieveDefaultQuota, "client")
    def test_execute(self, mock_client):
        retrieve_default_quota = base.RetrieveDefaultQuota(self.cloud)
        self.assertRetrieveQuota(
            mock_client.quotas.defaults,
            retrieve_default_quota.execute(self.tenant_id)
        )


class TestEnsureTenantQuota(TestBaseQuota):
    @patch.object(base.EnsureTenantQuota, "client")
    def test_execute(self, mock_client):
        ensure_tenant_quota = base.EnsureTenantQuota(self.cloud)
        self.assertEnsureQuota(mock_client.quotas.update,
                               self.tenant_id,
                               ensure_tenant_quota.execute(self.quota_info,
                                                           self.tenant_info))


class TestEnsureDefaultQuota(TestBaseQuota):
    @patch.object(base.EnsureDefaultQuota, "client")
    def test_execute(self, mock_client):
        ensure_default_quota = base.EnsureDefaultQuota(self.cloud)
        self.assertEnsureQuota(mock_client.quota_classes.update,
                               "default",
                               ensure_default_quota.execute(self.quota_info))
