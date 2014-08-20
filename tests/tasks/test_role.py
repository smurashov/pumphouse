import unittest
from mock import Mock, patch

from pumphouse import task
from pumphouse.tasks import role
from pumphouse.exceptions import keystone_excs
from taskflow.patterns import linear_flow


class TestRoleCase(unittest.TestCase):
    def setUp(self):
        self.dummy_id = '123'
        self.role_info = {
            'name': 'dummy'
        }

        self.role = Mock()
        self.role.to_dict.return_value = {}

        self.dst = Mock()

        self.cloud = Mock()
        self.cloud.keystone.roles.get.return_value = self.dummy_id
        self.cloud.keystone.roles.find.return_value = self.role
        self.cloud.keystone.roles.create.return_value = self.role


class TestRetrieveRole(TestRoleCase):
    def test_retrieve(self):
        retrieve_role = role.RetrieveRole(self.cloud)

        # Assures this is the instance of task.BaseRetrieveTask
        self.assertIsInstance(retrieve_role, task.BaseRetrieveTask)

        retrieve_role.retrieve(self.dummy_id)

        # Assures that cloud.keystone.roles.get is called with the same id
        # that was passed to retrieve method
        self.cloud.keystone.roles.get.assert_called_once_with(self.dummy_id)


class TestEnsureRole(TestRoleCase):
    def test_execute(self):
        ensure_role = role.EnsureRole(self.cloud)

        # Assures this is the instance of task.BaseRetrieveTask
        self.assertIsInstance(ensure_role, task.BaseCloudTask)

        # Assures that no cloud.keystone.roles.create method is not called
        # if cloud.keystone.roles.find does not raise Not Found exception
        # i.e. role is found by its name
        ensure_role.execute(self.role_info)
        self.assertFalse(self.cloud.keystone.roles.create.called)

    def test_execute_not_found(self):
        ensure_role = role.EnsureRole(self.cloud)

        # In case if Not Found exception is raised by ...find call
        # assures that cloud.keystone.roles.create is called
        self.cloud.keystone.roles.find.side_effect = keystone_excs.NotFound
        ensure_role.execute(self.role_info)
        self.cloud.keystone.roles.create.assert_called_once_with(name="dummy")


class TestMigrateRole(TestRoleCase):
    @patch.object(linear_flow.Flow, 'add')
    def test_migrate_role(self, mock_flow):
        mock_flow.return_value = self.dummy_id
        store = {}

        (flow, store) = role.migrate_role(
            self.role,
            self.dst,
            store,
            self.dummy_id
        )
        # Assures linear_flow.Flow().add is called
        self.assertTrue(mock_flow.called)

        # Assures that new flow is added to store after execution
        self.assertNotEqual({}, store)


if __name__ == '__main__':
    unittest.main()
