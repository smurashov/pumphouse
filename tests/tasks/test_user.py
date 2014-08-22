import unittest

from pumphouse.tasks import user
from mock import patch, Mock
from pumphouse import task
from pumphouse.exceptions import keystone_excs


class TestUser(unittest.TestCase):
    def setUp(self):
        self.user_id = "uid123"
        self.tenant_id = "tid456"
        self.role_id = "rid456"
        self.user_info = {
            "id": self.user_id,
            "name": "Poupkine Vassily",
            "email": "vpoupkine@email.com",
            "enabled": True
        }
        self.tenant_info = {
            "id": self.tenant_id
        }
        self.role_info = {
            "id": self.role_id
        }

        self.user = Mock()
        self.user.id = self.user_id
        self.user.to_dict.return_value = self.user_info

        self.dst = Mock()

        self.cloud = Mock()
        self.cloud.keystone.users.find.return_value = self.user
        self.cloud.keystone.users.get.return_value = self.user
        self.cloud.keystone.users.create.return_value = self.user

    def ensure_user(self, user, tenant_info, is_orphan=False):
        self.cloud.keystone.users.find.side_effect = keystone_excs.NotFound

        if is_orphan:
            user.execute(self.user_info)
        else:
            user.execute(self.user_info, tenant_info)

        self.cloud.keystone.users.create.assert_called_once_with(
            name=self.user_info["name"],
            password="default",
            email=self.user_info["email"],
            tenant_id=tenant_info["id"] if tenant_info else None,
            enabled=self.user_info["enabled"]
        )
        self.user.to_dict.assert_called_once_with()


class TestRetrieveUser(TestUser):
    def test_execute(self):
        retrieve_user = user.RetrieveUser(self.cloud)
        self.assertIsInstance(retrieve_user, task.BaseCloudTask)

        retrieve_user.execute(self.user_id)
        self.cloud.keystone.users.get.assert_called_once_with(self.user_id)
        self.cloud.identity.fetch.assert_called_once_with(self.user_id)
        self.user.to_dict.assert_called_once_with()


class TestEnsureUser(TestUser):
    def test_execute(self):
        ensure_user = user.EnsureUser(self.cloud)
        self.assertIsInstance(ensure_user, task.BaseCloudTask)

        ensure_user.execute(self.user_info, self.tenant_info)
        self.cloud.keystone.users.find.assert_called_once_with(
            name=self.user_info["name"])
        self.user.to_dict.assert_called_once_with()

    def test_execute_exception_tenant_info(self):
        self.ensure_user(user.EnsureUser(self.cloud), self.tenant_info)

    def test_execute_exception_no_tenant_info(self):
        self.ensure_user(user.EnsureUser(self.cloud), None)


class TestEnsureOrphanUser(TestUser):
    def test_execute(self):
        self.ensure_user(user.EnsureOrphanUser(self.cloud), None, True)


class TestEnsureUserRole(TestUser):
    def test_execute(self):
        ensure_user_role = user.EnsureUserRole(self.cloud)
        self.assertIsInstance(ensure_user_role, task.BaseCloudTask)

        info = ensure_user_role.execute(self.user_info,
                                        self.role_info,
                                        self.tenant_info)

        self.assertEqual(info, self.user_info)
        self.cloud.keystone.tenants.add_user.assert_called_once_with(
            self.tenant_id, self.user_id, self.role_id
        )

    def test_execute_exception(self):
        user.EnsureUserRole(self.cloud).execute(
            self.user_info,
            self.role_info,
            self.tenant_info
        )

        self.cloud.keystone.tenants.add_user.assert_called_once_with(
            self.tenant_id, self.user_id, self.role_id
        )


class TestMigrateMembership(TestUser):
    @patch.object(user, "EnsureUserRole")
    def test_migrate_membership(self, ensure_user_role_mock):
        store = {}
        (task, store) = user.migrate_membership(
            self.user,
            self.dst,
            store,
            self.user_id,
            self.role_id,
            self.tenant_id
        )

        self.assertTrue(ensure_user_role_mock.called)
        self.assertNotEqual(store, {})


class TestMigrateUser(TestUser):
    @patch.object(user, "EnsureUser")
    @patch.object(user, "RetrieveUser")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_user(self, flow_mock,
                          retrieve_user_mock, ensure_user_mock):

        store = {}
        (flow, store) = user.migrate_user(
            self.user,
            self.dst,
            store,
            self.user_id,
            self.tenant_id
        )

        flow_mock.assert_called_once_with("migrate-user-%s" % self.user_id)
        self.assertEqual(retrieve_user_mock.call_count, 1)
        self.assertEqual(ensure_user_mock.call_count, 1)
        self.assertNotEqual(store, {})

    @patch.object(user, "EnsureOrphanUser")
    @patch.object(user, "RetrieveUser")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_orphan_user(self, flow_mock,
                                 retrieve_user_mock, ensure_orphan_user_mock):
        store = {}
        (flow, store) = user.migrate_user(
            self.user,
            self.dst,
            store,
            self.user_id,
            None
        )

        flow_mock.assert_called_once_with("migrate-user-%s" % self.user_id)
        self.assertEqual(retrieve_user_mock.call_count, 1)
        self.assertEqual(ensure_orphan_user_mock.call_count, 1)
        self.assertNotEqual(store, {})


if __name__ == '__main__':
    unittest.main()
