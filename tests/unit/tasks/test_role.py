import unittest
from mock import Mock, patch, call

from pumphouse import task
from pumphouse.tasks import role
from pumphouse.exceptions import keystone_excs


class TestRoleCase(unittest.TestCase):
    def setUp(self):
        self.dummy_id = "123"
        self.role_info = {
            "name": "dummy"
        }

        self.role = Mock()
        self.role.to_dict.return_value = dict(self.role_info,
                                              id=self.dummy_id)

        self.context = Mock()
        self.context.store = {}

        self.cloud = Mock()
        self.cloud.keystone.roles.get.return_value = self.role
        self.cloud.keystone.roles.find.return_value = self.role
        self.cloud.keystone.roles.create.return_value = self.role


class TestRetrieveRole(TestRoleCase):
    def test_retrieve_is_task(self):
        retrieve_role = role.RetrieveRole(self.cloud)
        self.assertIsInstance(retrieve_role, task.BaseCloudTask)

    def test_retrieve(self):
        retrieve_role = role.RetrieveRole(self.cloud)
        role_info = retrieve_role.execute(self.dummy_id)
        self.cloud.keystone.roles.get.assert_called_once_with(self.dummy_id)
        self.assertEqual("123", role_info["id"])
        self.assertEqual("dummy", role_info["name"])


class TestEnsureRole(TestRoleCase):
    def test_execute(self):
        ensure_role = role.EnsureRole(self.cloud)
        ensure_role.execute(self.role_info)

        self.assertIsInstance(ensure_role, task.BaseCloudTask)
        self.cloud.keystone.roles.find.assert_called_once_with(
            name=self.role_info["name"]
        )
        self.assertFalse(self.cloud.keystone.roles.create.called)

    def test_execute_not_found(self):
        self.cloud.keystone.roles.find.side_effect = keystone_excs.NotFound

        ensure_role = role.EnsureRole(self.cloud)
        ensure_role.execute(self.role_info)

        self.cloud.keystone.roles.create.assert_called_once_with(
            name=self.role_info["name"]
        )


class TestMigrateRole(TestRoleCase):

    @patch.object(role, "EnsureRole")
    @patch.object(role, "RetrieveRole")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_role(self, mock_flow,
                          mock_retrieve_role, mock_ensure_role):
        flow = role.migrate_role(
            self.context,
            self.dummy_id,
        )

        mock_flow.assert_called_once_with("migrate-role-%s" % self.dummy_id)
        self.assertEqual(
            mock_flow().add.call_args,
            call(
                mock_retrieve_role(),
                mock_ensure_role()
            )
        )
        self.assertEqual(
            {"role-%s-retrieve" % self.dummy_id: self.dummy_id},
            self.context.store,
        )


if __name__ == "__main__":
    unittest.main()
