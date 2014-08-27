import unittest
from mock import patch, Mock

from pumphouse import base


class TestBase(unittest.TestCase):
    def setUp(self):
        self.identity = "dummy_id"
        self.identity2 = "dummy_id2"

        self.cloud_config = {
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
            "endpoint": self.cloud_config
        }
        self.target = Mock()
        self.driver = Mock(return_value=self.identity)
        self.driver.return_value = self.identity
        self.driver.from_dict.return_value = ()

        self.cloud_driver = self.driver
        self.identity_driver = self.driver

        self.cloud = Mock()
        self.events = []

        self.service = base.Service(
            self.config.copy(),
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
                         {"endpoint": self.cloud_config})
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
            identity=self.identity, endpoint=self.cloud_config)

    def test_make(self):
        self.service.make(identity=self.identity2)
        self.identity_driver.from_dict.assert_called_once_with(
            identity=self.identity2, endpoint=self.cloud_config)

    @patch("pumphouse.management.cleanup")
    @patch("pumphouse.management.setup")
    def test_reset_with_workloads(self, mock_setup, mock_cleanup):
        cloud = self.service.reset(self.events, self.cloud)

        self.assertEqual(cloud, self.cloud)
        mock_cleanup.assert_called_once_with(self.events,
                                             self.cloud,
                                             self.service.target)
        mock_setup.assert_called_once_with(self.events,
                                           self.cloud,
                                           self.service.target,
                                           workloads=self.config["workloads"])

    @patch("pumphouse.management.cleanup")
    @patch("pumphouse.management.setup")
    def test_reset_with_populate(self, mock_setup, mock_cleanup):
        self.service.workloads_config = None
        cloud = self.service.reset(self.events, self.cloud)

        self.assertEqual(cloud, self.cloud)
        mock_cleanup.assert_called_once_with(self.events,
                                             self.cloud,
                                             self.service.target)
        mock_setup.assert_called_once_with(
            self.events, self.cloud, self.service.target,
            self.config["populate"]["num_tenants"],
            self.config["populate"]["num_servers"])

    @patch("pumphouse.management.cleanup")
    @patch("pumphouse.management.setup")
    def test_reset_with_populate_default(self, mock_setup, mock_cleanup):
        self.service.workloads_config = None
        self.service.populate_config = {}
        self.service.reset(self.events, self.cloud)

        # Assuring that if there are no num_servers and num_tenants present
        # in populate_config default values are used
        mock_setup.assert_called_once_with(self.events,
                                           self.cloud,
                                           self.service.target,
                                           2,
                                           2)

    @patch("pumphouse.management.cleanup")
    @patch("pumphouse.management.setup")
    def test_reset_without_configs(self, mock_setup, mock_cleanup):
        self.service.workloads_config = None
        self.service.populate_config = None
        self.service.reset(self.events, self.cloud)

        # Case when none of workloads_config or populate_config are dicts
        self.assertFalse(mock_setup.called)


if __name__ == '__main__':
    unittest.main()
