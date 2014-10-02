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

from pumphouse import exceptions
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
        self.cloud = mock.Mock(spec=["nova"])
        if self.task_class:
            self.task = self.task_class(self.cloud)


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
            [mock.call(existing_net.to_dict.return_value, self.network_info)],
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
