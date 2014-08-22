import unittest

from pumphouse.exceptions import nova_excs
from pumphouse.tasks import flavor
from pumphouse import task
from mock import patch, Mock
from taskflow.patterns import linear_flow


class TestFlavor(unittest.TestCase):
    def setUp(self):
        self.dummy_id = "123"
        self.flavor_info = {
            "name": "dummy",
            "ram": 100,
            "vcpus": 2,
            "disk": 512,
            "id": self.dummy_id,
            "OS-FLV-EXT-DATA:ephemeral": True,
            "swap": 0,
            "rxtx_factor": 100,
            "os-flavor-access:is_public": True
        }

        self.flavor = Mock()
        self.flavor.to_dict.return_value = {}

        self.dst = Mock()

        self.cloud = Mock()
        self.cloud.nova.flavors.get.return_value = self.flavor
        self.cloud.nova.flavors.create.return_value = self.flavor


class TestRetrieveFlavor(TestFlavor):
    def test_execute(self):
        retrieve_flavor = flavor.RetrieveFlavor(self.cloud)
        self.assertIsInstance(retrieve_flavor, task.BaseCloudTask)

        retrieve_flavor.execute(self.dummy_id)
        self.cloud.nova.flavors.get.assert_called_once_with(self.dummy_id)


class TestEnsureFlavor(TestFlavor):
    def test_execute(self):
        ensure_flavor = flavor.EnsureFlavor(self.cloud)

        self.assertIsInstance(ensure_flavor, task.BaseCloudTask)

        ensure_flavor.execute(self.flavor_info)
        self.assertFalse(self.cloud.nova.flavors.create.called)

    def test_execute_not_found(self):
        ensure_flavor = flavor.EnsureFlavor(self.cloud)

        # In case if Not Found exception is raised by ...find call
        # assures that cloud.nova.flavors.create is called
        self.cloud.nova.flavors.get.side_effect = nova_excs.NotFound(
            "404 Flavor Not Found")

        ensure_flavor.execute(self.flavor_info)

        self.cloud.nova.flavors.create.assert_called_once_with(
            self.flavor_info["name"],
            self.flavor_info["ram"],
            self.flavor_info["vcpus"],
            self.flavor_info["disk"],
            flavorid=self.flavor_info["id"],
            ephemeral=self.flavor_info["OS-FLV-EXT-DATA:ephemeral"],
            swap=self.flavor_info["swap"] or 0,
            rxtx_factor=self.flavor_info["rxtx_factor"],
            is_public=self.flavor_info["os-flavor-access:is_public"]
        )


class TestMigrateFlavor(TestFlavor):

    @patch.object(linear_flow.Flow, "add")
    def test_migrate_flavor(self, mock_flow):
        mock_flow.return_value = self.dummy_id

        store = {}

        (flow, store) = flavor.migrate_flavor(
            self.flavor,
            self.dst,
            store,
            self.dummy_id
        )

        self.assertTrue(mock_flow.called)
        self.assertNotEqual({}, store)


if __name__ == '__main__':
    unittest.main()
