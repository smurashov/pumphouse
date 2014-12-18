import unittest

from mock import patch, Mock, call

from pumphouse.tasks import snapshot
from pumphouse import task


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
        self.test_user_id = '777'
        self.test_tenant_id = '888'
        self.test_server_name = "test-server"
        self.test_snapshot_info = AttrDict({
            "id": self.test_snapshot_id,
            "status": "active",
        })
        self.test_server_info = AttrDict({
            "id": self.test_server_id,
            "user_id": self.test_user_id,
            "tenant_id": self.test_tenant_id,
            "name": self.test_server_name,
        })

        self.context = Mock()
        self.context.store = {}

        self.cloud = Mock()
        self.cloud.nova.servers.create_image.return_value = \
            self.test_snapshot_id
        self.cloud.glance.images.get.return_value = self.test_snapshot_info

        self.utils = Mock()
        self.utils.wait_for.return_value = self.test_snapshot_id


class TestSnapshotServer(TestSnapshot):
    def test_execute(self):
        ensure_snapshot = snapshot.SnapshotServer(self.cloud)
        self.assertIsInstance(ensure_snapshot, task.BaseCloudTask)

        snapshot_id = ensure_snapshot.execute(self.test_server_info)
        expected_name = "{}-snapshot-{}".format(self.test_server_name,
                                                self.test_server_id)
        self.cloud.nova.servers.create_image.assert_called_once_with(
            self.test_server_id, expected_name)

        self.assertEqual(snapshot_id, self.test_snapshot_id)

    def test_execute_exception(self):
        self.cloud.nova.servers.create_image.side_effect = Exception

        with self.assertRaises(Exception):
            snapshot.SnapshotServer(self.cloud).execute(self.test_server_info)


class TestMigrateEphemeralStorage(TestSnapshot):

    @patch("pumphouse.tasks.image.EnsureSingleImage")
    @patch.object(snapshot, "SnapshotServer")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_snapshot(self, flow_mock,
                              ensure_snapshot_mock,
                              ensure_image_mock):
        flow = snapshot.migrate_snapshot(
            self.context,
            self.test_server_info,
        )

        flow_mock.assert_called_once_with("migrate-ephemeral-"
                                          "storage-server-{}"
                                          .format(self.test_server_id))
        self.assertEqual(flow.add.call_args_list,
                         [call(ensure_snapshot_mock()),
                          call(ensure_image_mock())])


if __name__ == '__main__':
    unittest.main()
