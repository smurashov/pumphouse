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

from pumphouse import flows
from pumphouse.tasks import network as network_tasks


LOG = logging.getLogger(__name__)

migrate_network = flows.register("network")


@migrate_network.add("FlatDHCP")
def migrate_network_with_nova_flatdhcp(context, network_id):
    network = context.src.nova.networks.get(network_id)
    network_flow, store = network_tasks.migrate_network(network_id)
    return network_flow, store
