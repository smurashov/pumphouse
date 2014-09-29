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

import netaddr

from pumphouse import exceptions
from pumphouse import task
from pumphouse.tasks import floating_ip as fip_tasks
from taskflow.patterns import graph_flow

LOG = logging.getLogger(__name__)


class RetrieveAllNetworks(task.BaseCloudTask):
    def execute(self):
        # FIXME(yorik-sar): Who the hell needs nova-network with such API?!
        networks = self.cloud.nova.networks.list()
        return {
            "by-name": dict((net.label, net) for net in networks),
            "by-id": dict((net.id, net) for net in networks),
        }


class RetrieveNetworkById(task.BaseCloudTask):
    def execute(self, all_networks, network_id):
        network = all_networks["by-id"][network_id]
        return network.to_dict()


class RetrieveNetworkByName(task.BaseCloudTask):
    def execute(self, all_networks, network_name):
        network = all_networks["by-name"][network_name]
        return network.to_dict()


class EnsureNetwork(task.BaseCloudTask):
    def execute(self, network_info):
        try:
            cidr = network_info['cidr']
            if cidr:
                s = netaddr.IPSet(cidr)
                network_info['cidr'] = str(list(s.iter_cidrs())[0])
            network = self.cloud.nova.networks.create(**network_info)
        except exceptions.nova_excs.Conflict:
            LOG.exception("Conflicts: %s", network_info)
            raise
        else:
            LOG.info("Created: %s", network.to_dict())
            return network.to_dict()


class EnsureNic(task.BaseCloudTask):
    def execute(self, network_info, address):
        return {
            "net-id": network_info['id'],
            "v4-fixed-ip": address,  # TODO(yorik-sar): IPv6
        }


def migrate_nic(context, network_name, address):
    if address["OS-EXT-IPS:type"] == 'floating':
        floating_ip = address["addr"]
        floating_ip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
        if floating_ip_retrieve in context.store:
            return None, None
        floating_ip_flow = fip_tasks.migrate_floating_ip(context, floating_ip)
        return floating_ip_flow, None
    elif address["OS-EXT-IPS:type"] == 'fixed':
        fixed_ip = address["addr"]
        fixed_ip_retrieve = "fixed-ip-{}-retrieve".format(fixed_ip)
        fixed_ip_nic = "fixed-ip-{}-nic".format(fixed_ip)
        if fixed_ip_retrieve in context.store:
            return None, fixed_ip_nic
        flow = graph_flow.Flow("migrate-{}-fixed-ip".format(fixed_ip))
        network_flow, network_ensure = migrate_network(
            context, network_name=network_name)
        if network_flow is not None:
            flow.add(network_flow)
        flow.add(EnsureNic(context.dst_cloud,
                           name=fixed_ip_nic,
                           provides=fixed_ip_nic,
                           rebind=[network_ensure, fixed_ip_retrieve]))
        context.store[fixed_ip_retrieve] = fixed_ip
        return flow, fixed_ip_nic


def migrate_network(context, network_id=None, network_name=None):
    assert (network_id, network_name).count(None) == 1
    by_id = network_id is not None
    all_src_networks = "networks-src"
    all_dst_networks = "networks-dst"
    all_src_networks_retrieve = "networks-src-retrieve"
    all_dst_networks_retrieve = "networks-dst-retrieve"
    if by_id:
        network_binding = "network-{}".format(network_id)
        network_retrieve = "{}-retrieve".format(network_id)
        network_ensure = "{}-ensure".format(network_id)
    else:
        network_binding = "network-{}".format(network_name)
        network_retrieve = "{}-retrieve".format(network_name)
        network_ensure = "{}-ensure".format(network_name)
    if network_binding in context.store:
        return None, network_ensure
    flow = graph_flow.Flow("migrate-{}".format(network_binding))
    if all_src_networks_retrieve not in context.store:
        flow.add(RetrieveAllNetworks(context.src_cloud,
                                     name=all_src_networks,
                                     provides=all_src_networks))
        context.store[all_src_networks_retrieve] = None
    if all_dst_networks_retrieve not in context.store:
        flow.add(RetrieveAllNetworks(context.dst_cloud,
                                     name=all_dst_networks,
                                     provides=all_dst_networks))
        context.store[all_dst_networks_retrieve] = None
    if by_id:
        flow.add(RetrieveNetworkById(
            context.src_cloud,
            name=network_retrieve,
            provides=network_retrieve,
            rebind=[all_src_networks, network_binding]))
    else:
        flow.add(RetrieveNetworkByName(
            context.src_cloud,
            name=network_retrieve,
            provides=network_retrieve,
            rebind=[all_src_networks, network_binding]))
    flow.add(EnsureNetwork(context.dst_cloud,
                           name=network_ensure,
                           provides=network_ensure,
                           rebind=[network_retrieve]))
    if by_id:
        context.store[network_binding] = network_id
    else:
        context.store[network_binding] = network_name
    return flow, network_ensure
