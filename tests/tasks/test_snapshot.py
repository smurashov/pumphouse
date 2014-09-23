import unittest
from mock import patch, Mock
from pumphouse.tasks import snapshot
from pumphouse import task
from taskflow.patterns import linear_flow


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self
        self._info = self

    def to_dict(self):
        return self.copy()


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.test_server_id = "123"
        self.test_snapshot_id = "456"
        self.test_snapshot_info = AttrDict({
            "id": self.test_snapshot_id,
            "status": "active"
        })
        self.test_user_id = '777'

        self.context = Mock()

        self.cloud = Mock()
        self.cloud.nova.servers.create_image.return_value = \
            self.test_snapshot_id
        self.cloud.glance.images.get.return_value = self.test_snapshot_info

        self.utils = Mock()
        self.utils.wait_for.return_value = self.test_snapshot_id


class TestEnsureSnapshot(TestSnapshot):
    def test_execute(self):
        ensure_snapshot = snapshot.EnsureSnapshot(self.cloud)
        self.assertIsInstance(ensure_snapshot, task.BaseCloudTask)

        snapshot_id = ensure_snapshot.execute(self.test_server_id)
        self.cloud.nova.servers.create_image.assert_called_once_with(
            self.test_server_id,
            "pumphouse-snapshot-%s" % self.test_server_id)

        self.assertEqual(snapshot_id, self.test_snapshot_id)

    def test_execute_exception(self):
        self.cloud.nova.servers.create_image.side_effect = Exception

        with self.assertRaises(Exception):
            snapshot.EnsureSnapshot(self.cloud).execute(self.test_server_id)


class TestMigrateEphemeralStorage(TestSnapshot):
    @patch.object(linear_flow.Flow, "add")
    def test_migrate_snapshot(self, mock_flow_add):
        store = {}

        (flow, store) = snapshot.migrate_snapshot(
            self.context,
            store,
            self.test_server_id,
            self.test_user_id
        )

        self.assertEqual(mock_flow_add.call_count, 2)


if __name__ == '__main__':
    unittest.main()
