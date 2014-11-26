import unittest

import mock

from pumphouse import base
from pumphouse.tasks import reset


class TestBase(unittest.TestCase):
    def setUp(self):
        self.identity = "dummy_id"
        self.identity2 = "dummy_id2"

        self.cloud_endpoint = {
            "auth_url": "auth_url"
        }
        self.config = {
            "identity": {"a": self.identity},
            "populate": {
                "num_tenants": 13,
                "num_servers": 42
            },
            "workloads": {"c": "abc123"},
            "urls": ["a", "b", "c"],
            "endpoint": self.cloud_endpoint,
        }
        self.target = "fakecloud"
        self.driver = mock.Mock(return_value=self.identity)
        self.driver.return_value = self.identity
        self.driver.from_dict.return_value = ()

        self.cloud_driver = self.driver
        self.identity_driver = self.driver

        self.cloud = mock.Mock()
        self.events = mock.Mock()

        self.service = base.Service(
            self.config.copy(),
            {},  # plugins
            self.target,
            self.cloud_driver,
            self.identity_driver
        )


class TestService(TestBase):
    def test___init__(self):

        self.assertEqual(self.service.identity_config, self.config["identity"])
        self.assertEqual(self.service.populate_config, self.config["populate"])
        self.assertEqual(self.service.workloads_config,
                         self.config["workloads"])
        self.assertEqual(self.service.cloud_urls, self.config["urls"])
        self.assertEqual(self.service.cloud_config,
                         {"endpoint": self.cloud_endpoint})
        self.assertEqual(self.service.target, self.target)
        self.assertEqual(self.service.cloud_driver, self.cloud_driver)
        self.assertEqual(self.service.identity_driver, self.identity_driver)

    def test_check(self):
        self.service.check(self.cloud)
        self.cloud.ping.assert_called_once_with()

    def test_make_with_none(self):
        self.service.make(identity=None)
        self.identity_driver.assert_called_once_with(a=self.identity)
        self.identity_driver.from_dict.assert_called_once_with(
            self.target, self.identity, {"endpoint": self.cloud_endpoint})

    def test_make(self):
        self.service.make(identity=self.identity2)
        self.identity_driver.from_dict.assert_called_once_with(
            self.target, self.identity2, {"endpoint": self.cloud_endpoint})

    @mock.patch("pumphouse.tasks.base.TaskflowRunner")
    def test_reset_with_workloads(self, mock_runner):
        self.service.reset(self.events, self.cloud)

        runner = mock_runner.return_value
        self.assertEqual(
            runner.get_resource.call_args_list,
            [
                mock.call(reset.CleanupWorkload, {"id": self.cloud.name}),
                mock.call(reset.SetupWorkload, {
                    "id": self.cloud.name,
                    "populate": self.config["populate"],
                    "workloads": self.config["workloads"],
                }),
            ],
        )
        resource = runner.get_resource.return_value
        self.assertEqual(
            runner.add.call_args_list,
            [mock.call(resource.delete), mock.call(resource.create)],
        )

    @mock.patch("pumphouse.tasks.base.TaskflowRunner")
    def test_reset_with_populate(self, mock_runner):
        self.service.workloads_config = None
        self.service.reset(self.events, self.cloud)

        runner = mock_runner.return_value
        self.assertEqual(
            runner.get_resource.call_args_list,
            [
                mock.call(reset.CleanupWorkload, {"id": self.cloud.name}),
                mock.call(reset.SetupWorkload, {
                    "id": self.cloud.name,
                    "populate": self.config["populate"],
                    "workloads": {},
                }),
            ],
        )
        resource = runner.get_resource.return_value
        self.assertEqual(
            runner.add.call_args_list,
            [mock.call(resource.delete), mock.call(resource.create)],
        )

    @mock.patch("pumphouse.tasks.base.TaskflowRunner")
    def test_reset_with_populate_default(self, mock_runner):
        self.service.workloads_config = None
        self.service.populate_config = {}
        self.service.reset(self.events, self.cloud)

        # Assuring that if there are no num_servers and num_tenants present
        # in populate_config default values are used
        runner = mock_runner.return_value
        self.assertEqual(
            runner.get_resource.call_args_list,
            [
                mock.call(reset.CleanupWorkload, {"id": self.cloud.name}),
                mock.call(reset.SetupWorkload, {
                    "id": self.cloud.name,
                    "populate": {},
                    "workloads": {},
                }),
            ],
        )
        resource = runner.get_resource.return_value
        self.assertEqual(
            runner.add.call_args_list,
            [mock.call(resource.delete), mock.call(resource.create)],
        )

    @mock.patch("pumphouse.tasks.base.TaskflowRunner")
    def test_reset_without_configs(self, mock_runner):
        self.service.workloads_config = None
        self.service.populate_config = None
        self.service.reset(self.events, self.cloud)

        # Case when none of workloads_config or populate_config are dicts
        runner = mock_runner.return_value
        self.assertEqual(
            runner.get_resource.call_args_list,
            [
                mock.call(reset.CleanupWorkload, {"id": self.cloud.name}),
            ],
        )
        resource = runner.get_resource.return_value
        self.assertEqual(
            runner.add.call_args_list,
            [mock.call(resource.delete)],
        )


if __name__ == '__main__':
    unittest.main()
