from mock import Mock, patch, call
import unittest

from pumphouse.exceptions import nova_excs
from pumphouse.tasks import flavor
from pumphouse import task


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

        self.context = Mock()
        self.context.store = {}

        self.cloud = Mock()
        self.cloud.nova.flavors.get.return_value = self.flavor
        self.cloud.nova.flavors.create.return_value = self.flavor


class TestRetrieveFlavor(TestFlavor):
    def test_execute(self):
        retrieve_flavor = flavor.RetrieveFlavor(self.cloud)
        retrieve_flavor.execute(self.dummy_id)

        self.assertIsInstance(retrieve_flavor, task.BaseCloudTask)
        self.cloud.nova.flavors.get.assert_called_once_with(self.dummy_id)


class TestEnsureFlavor(TestFlavor):
    def test_execute(self):
        ensure_flavor = flavor.EnsureFlavor(self.cloud)
        ensure_flavor.execute(self.flavor_info)

        self.assertIsInstance(ensure_flavor, task.BaseCloudTask)
        self.cloud.nova.flavors.get.assert_called_once_with(
            self.flavor_info["id"]
        )
        self.assertFalse(self.cloud.nova.flavors.create.called)

    def test_execute_not_found(self):
        self.cloud.nova.flavors.get.side_effect = nova_excs.NotFound(
            "404 Flavor Not Found")

        ensure_flavor = flavor.EnsureFlavor(self.cloud)
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

    @patch.object(flavor, "EnsureFlavor")
    @patch.object(flavor, "RetrieveFlavor")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_flavor(self, mock_flow,
                            mock_retrieve_flavor, mock_ensure_flavor):
        flow = flavor.migrate_flavor(
            self.context,
            self.dummy_id,
        )

        mock_flow.assert_called_once_with("migrate-flavor-%s" % self.dummy_id)
        self.assertEqual(
            mock_flow().add.call_args,
            call(
                mock_retrieve_flavor(),
                mock_ensure_flavor()
            )
        )
        self.assertEqual(
            {"flavor-%s-retrieve" % self.dummy_id: self.dummy_id},
            self.context.store,
        )


if __name__ == '__main__':
    unittest.main()
