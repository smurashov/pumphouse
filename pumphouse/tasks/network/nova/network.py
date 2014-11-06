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
from taskflow.patterns import graph_flow

from pumphouse import exceptions
from pumphouse import task
from . import floating_ip as fip_tasks

LOG = logging.getLogger(__name__)


class RetrieveAllNetworks(task.BaseCloudTask):
    def execute(self):
        # FIXME(yorik-sar): Who the hell needs nova-network with such API?!
        networks = self.cloud.nova.networks.list()
        return {
            "by-label": dict((net.label, net.to_dict()) for net in networks),
            "by-id": dict((net.id, net.to_dict()) for net in networks),
        }


class RetrieveNetworkById(task.BaseCloudTask):
    def execute(self, all_networks, network_id):
        network = all_networks["by-id"][network_id]
        return network


class RetrieveNetworkByLabel(task.BaseCloudTask):
    def execute(self, all_networks, network_label):
        network = all_networks["by-label"][network_label]
        return network


class EnsureNetwork(task.BaseCloudTask):
    def verify(self, network, network_info):
        network_label = network["label"]
        for k, v in network.items():
            if k.endswith('_at') or k in ('id', 'host', 'vpn_public_address'):
                continue  # Skip timestamps and cloud-specific fields
            if v != network_info[k]:
                raise exceptions.Conflict("Network %s has different field %s" %
                                          (network_label, k))
        return network

    def execute(self, all_networks, network_info, tenant_info):
        network_label = network_info["label"]
        try:
            network = all_networks["by-label"][network_label]
        except KeyError:
            pass  # We'll create a new one
        else:  # Verify that existing one is a good one and return or fail
            return self.verify(network, network_info)
        try:
            cidr = network_info['cidr']
            if isinstance(cidr, list):
                s = netaddr.IPSet(cidr)
                network_info['cidr'] = str(list(s.iter_cidrs())[0])
            network_info['project_id'] = tenant_info['id']
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


def migrate_nic(context, network_label, address, tenant_id):
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
            context, network_label=network_label, tenant_id=tenant_id)
        if network_flow is not None:
            flow.add(network_flow)
        flow.add(EnsureNic(context.dst_cloud,
                           name=fixed_ip_nic,
                           provides=fixed_ip_nic,
                           rebind=[network_ensure, fixed_ip_retrieve]))
        context.store[fixed_ip_retrieve] = fixed_ip
        return flow, fixed_ip_nic


def migrate_network(context, network_id=None, network_label=None,
                    tenant_id=None):
    assert (network_id, network_label).count(None) == 1
    by_id = network_id is not None
    all_src_networks = "networks-src"
    all_dst_networks = "networks-dst"
    all_src_networks_retrieve = "networks-src-retrieve"
    all_dst_networks_retrieve = "networks-dst-retrieve"
    if by_id:
        network_binding = "network-{}".format(network_id)
    else:
        network_binding = "network-{}".format(network_label)
    network_retrieve = "{}-retrieve".format(network_binding)
    network_ensure = "{}-ensure".format(network_binding)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
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
        flow.add(RetrieveNetworkByLabel(
            context.src_cloud,
            name=network_retrieve,
            provides=network_retrieve,
            rebind=[all_src_networks, network_binding]))
    flow.add(EnsureNetwork(context.dst_cloud,
                           name=network_ensure,
                           provides=network_ensure,
                           rebind=[all_dst_networks, network_retrieve,
                                   tenant_ensure]))
    if by_id:
        context.store[network_binding] = network_id
    else:
        context.store[network_binding] = network_label
    return flow, network_ensure
