# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.

import unittest

import mock

from pumphouse import context
from pumphouse import exceptions
from pumphouse.tasks import floating_ip
from pumphouse.tasks import network


class TestNetwork(unittest.TestCase):
    task_class = None

    def setUp(self):
        self.network_info = {
            "label": "mynet",
            "created_at": "long_ago",
            "id": "123",
            "host": "that_one",
            "cidr": ["10.1.0.0", "10.1.0.1"],
        }
        self.cloud = mock.Mock(spec=["nova"], name="dst_cloud")
        if self.task_class:
            self.task = self.task_class(self.cloud)
        self.store = {}
        self.context = context.Context(
            mock.Mock(name="config"),
            self.cloud,
            mock.Mock(spec=["nova"], name="dst_cloud"),
            self.store,
        )


class TestEnsureNetwork(TestNetwork):
    task_class = network.EnsureNetwork

    @mock.patch.object(network.EnsureNetwork, "verify")
    def test_execute(self, mock_verify):
        all_networks = {"by-label": {}}
        rv = self.task.execute(all_networks, self.network_info)
        network_create = self.cloud.nova.networks.create
        self.assertEqual(rv, network_create.return_value.to_dict.return_value)
        self.assertEqual(mock_verify.call_count, 0)
        self.network_info["cidr"] = "10.1.0.0/31"
        self.assertEqual(
            network_create.call_args_list,
            [mock.call(**self.network_info)],
        )

    @mock.patch.object(network.EnsureNetwork, "verify", return_value=True)
    def test_execute_exists(self, mock_verify):
        existing_net = mock.Mock()
        all_networks = {"by-label": {self.network_info["label"]: existing_net}}
        rv = self.task.execute(all_networks, self.network_info)
        network_create = self.cloud.nova.networks.create
        self.assertEqual(network_create.call_count, 0)
        self.assertEqual(rv, mock_verify.return_value)
        self.assertEqual(
            mock_verify.call_args_list,
            [mock.call(existing_net, self.network_info)],
        )

    def test_verify(self):
        rv = self.task.verify(self.network_info, self.network_info)
        self.assertEqual(self.network_info, rv)

    def test_verify_ignores(self):
        other_net = self.network_info.copy()
        other_net.update({
            "id": "321",
            "created_at": "just_now",
            "host": "another_one",
        })
        rv = self.task.verify(other_net, self.network_info)
        self.assertEqual(rv, other_net)

    def test_verify_failes(self):
        other_net = self.network_info.copy()
        other_net.update({
            "cidr": ["10.2.0.0", "10.2.0.1"],
        })
        self.assertRaises(exceptions.Conflict, self.task.verify,
                          other_net, self.network_info)


class TestEnsureNic(TestNetwork):
    task_class = network.EnsureNic

    def test_execute(self):
        rv = self.task.execute(self.network_info, "1.2.3.4")
        self.assertEqual(rv, {
            "net-id": self.network_info["id"],
            "v4-fixed-ip": "1.2.3.4",
        })


class TestMigrateNic(TestNetwork):
    @mock.patch.object(floating_ip, "migrate_floating_ip")
    def test_migrate_floating_ip(self, mock_migrage_fip):
        address = {
            "addr": "1.2.3.4",
            "OS-EXT-IPS:type": "floating",
        }
        rv = network.migrate_nic(self.context, "mynet", address)
        self.assertEqual(rv, (mock_migrage_fip.return_value, None))
        self.assertEqual(
            mock_migrage_fip.call_args_list,
            [mock.call(self.context, "1.2.3.4")],
        )

    @mock.patch.object(floating_ip, "migrate_floating_ip")
    def test_migrate_floating_ip_dup(self, mock_migrage_fip):
        address = {
            "addr": "1.2.3.4",
            "OS-EXT-IPS:type": "floating",
        }
        self.store["floating-ip-1.2.3.4-retrieve"] = None
        rv = network.migrate_nic(self.context, "mynet", address)
        self.assertEqual(rv, (None, None))
        self.assertEqual(mock_migrage_fip.call_count, 0)

    @mock.patch.object(network, "migrate_network")
    @mock.patch.object(network, "EnsureNic")
    @mock.patch("taskflow.patterns.graph_flow.Flow")
    def test_migrate_fixed_ip(self, mock_flow, mock_ensure_nic,
                              mock_migrate_network):
        address = {
            "addr": "1.2.3.4",
            "OS-EXT-IPS:type": "fixed",
        }
        mock_migrate_network.return_value = mock.Mock(), mock.Mock()
        rv = network.migrate_nic(self.context, "mynet", address)
        self.assertEqual(rv, (mock_flow.return_value, "fixed-ip-1.2.3.4-nic"))
        self.assertEqual(
            mock_migrate_network.call_args_list,
            [mock.call(self.context, network_label="mynet")],
        )
        self.assertItemsEqual(
            mock_flow.return_value.add.call_args_list,
            [mock.call(mock_migrate_network.return_value[0]),
             mock.call(mock_ensure_nic.return_value)],
        )
        self.assertIn("fixed-ip-1.2.3.4-retrieve", self.store)

    @mock.patch.object(network, "migrate_network")
    def test_migrate_fixed_ip_dup(self, mock_migrate_network):
        address = {
            "addr": "1.2.3.4",
            "OS-EXT-IPS:type": "fixed",
        }
        self.store["fixed-ip-1.2.3.4-retrieve"] = None
        rv = network.migrate_nic(self.context, "mynet", address)
        self.assertEqual(rv, (None, "fixed-ip-1.2.3.4-nic"))
        self.assertEqual(mock_migrate_network.call_count, 0)

    @mock.patch("taskflow.patterns.graph_flow.Flow")
    def test_migrate_network(self, mock_flow):
        mocks = []
        for name in ["RetrieveAllNetworks", "RetrieveNetworkByLabel",
                     "EnsureNetwork"]:
            patcher = mock.patch.object(network, name)
            mocks.append(patcher.start())
            self.addCleanup(patcher.stop)
        rv = network.migrate_network(self.context, network_label="mynet")
        self.assertEqual(rv, (mock_flow.return_value, "network-mynet-ensure"))
        self.assertItemsEqual(
            mock_flow.return_value.add.call_args_list,
            [mock.call(m.return_value) for m in mocks + [mocks[0]]],
        )
        self.assertEqual(
            self.store,
            {
                "networks-src-retrieve": None,
                "networks-dst-retrieve": None,
                "network-mynet": "mynet",
            },
        )
