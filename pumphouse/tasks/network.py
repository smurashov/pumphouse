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

import logging

from pumphouse import exceptions
from pumphouse import flows
from pumphouse import task
from taskflow.patterns import linear_flow

LOG = logging.getLogger(__name__)

migrate_network = flows.register("network")


class RetrieveNetwork(task.BaseCloudTask):
    def execute(self, network_id):
        network = self.cloud.nova.networks.get(network_id)
        return network.to_dict()


class EnsureNetwork(task.BaseCloudTask):
    def execute(self, network_info):
        try:
            network = self.cloud.nova.networks.create(**network_info)
        except exceptions.nova_excs.Conflict:
            LOG.exception("Conflicts: %s", network_info)
            raise
        else:
            LOG("Created: %s", network.to_dict())
            return network.to_dict()


@migrate_network.add("flatdhcp")
def migrate_network(context, network_id):
    store = context.store
    network_binding = "network-{}".format(network_id)
    network_retrieve = "{}-retrieve".format(network_id)
    network_ensure = "{}-ensure".format(network_id)
    flow = linear_flow.Flow("migrate-{}".format(network_binding))
    flow.add(RetrieveNetwork(context.src,
                             name=network_retrieve,
                             provides=network_retrieve,
                             rebind=[network_binding]))
    flow.add(EnsureNetwork(context.dst,
                           name=network_ensure,
                           provides=network_ensure,
                           rebind=[network_retrieve]))
    store[network_binding] = network_id
    return flow, store
