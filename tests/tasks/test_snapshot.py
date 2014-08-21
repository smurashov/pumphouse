import unittest
from mock import patch, Mock
from pumphouse.tasks import snapshot
from pumphouse import task
from taskflow.patterns import linear_flow


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.dummy_id = "123"
        self.image_info = {
            "id": self.dummy_id
        }

        self.image = Mock()
        self.image.to_dict.return_value = {}

        self.dst = Mock()

        self.cloud = Mock()
        self.cloud.servers.create_image.return_value = self.dummy_id
        self.cloud.glance.images.get.return_value = self.image
        self.cloud.glance.images.create_image.return_value = self.image


class TestRetrieveImage(TestSnapshot):
    def test_execute(self):
        retrieve_image = snapshot.RetrieveImage(self.cloud)
        self.assertIsInstance(retrieve_image, task.BaseCloudTask)

        retrieve_image.execute(self.dummy_id)
        self.cloud.glance.images.get.assert_called_once_with(self.dummy_id)
        self.image.to_dict.assert_called_once_with()


class TestEnsureSnapshot(TestSnapshot):
    def test_execute(self):
        ensure_snapshot = snapshot.EnsureSnapshot(self.cloud)
        self.assertIsInstance(ensure_snapshot, task.BaseCloudTask)

        id = ensure_snapshot.execute(self.image_info)
        self.cloud.servers.create_image.assert_called_once_with(
            self.dummy_id,
            "pumphouse-snapshot-%s" % self.dummy_id)

        self.cloud.glance.images.get.assert_called_once_with(id)
        self.assertEqual(id, self.dummy_id)

    def test_execute_exception(self):
        self.cloud.glance.images.create_image.side_effect = Exception

        snapshot.EnsureSnapshot(self.cloud).execute(self.image_info)
        self.assertRaises(Exception)


class TestMigrateEphemeralStorage(TestSnapshot):
    @patch.object(linear_flow.Flow, "add")
    def test_migrate_ephemeral_storage(self, mock_flow_add):
        store = {}

        (flow, store) = snapshot.migrate_ephemeral_storage(
            self.image,
            self.dst,
            store,
            self.dummy_id
        )

        self.assertEqual(mock_flow_add.call_count, 2)


if __name__ == '__main__':
    unittest.main()
