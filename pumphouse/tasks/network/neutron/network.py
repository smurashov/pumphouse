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

from pumphouse import task
from taskflow.patterns import graph_flow
from . import utils

LOG = logging.getLogger(__name__)


def create_network(neutron, net_info):
    try:
        return neutron.create_network({'network': net_info})['network']
    except Exception as e:
        raise e


class RetrieveNeutronNetworks(task.BaseCloudTask):

    def execute(self):
        return self.cloud.neutron.list_networks()['networks']


class RetrieveNetworkById(task.BaseCloudTask):

    def execute(self, sourceNeutronNetworks, net_id):
        for net in sourceNeutronNetworks:
            if (net['id'] == net_id):
                LOG.info("Match network %s" % net_id)
                return net


class EnsureNetwork(task.BaseCloudTask):

    def execute(self, networks, net_info, tenant_info):

        for net in networks:
            if (net['name'] == net_info['name']):
                LOG.info("Network %s is allready exists, name: %s" %
                         (net_info['id'], net['name']))
                return net

        restrict_cloud = self.cloud.restrict(
            tenant_name=tenant_info["name"])

        LOG.info("Network %s not exists" % net_info['id'])

        net_info['tenant_id'] = tenant_info['id']

        network = create_network(restrict_cloud.neutron, {
            'name': net_info['name']
        })

        LOG.info("Network %s created: %s" % (network['id'], str(network)))

        return network


def migrate_network(context, network_id, tenant_info):

    network_binding = network_id

    network_retrieve = "network-{}-retrieve".format(
        network_binding)
    network_ensure = "network-{}-ensure".format(
        network_binding)

    if (network_binding in context.store):
        return None, network_retrieve

    context.store[network_binding] = network_id

    f = graph_flow.Flow("neutron-network-migration-{}".format(network_binding))

    all_dst, all_src, all_src_retrieve, all_dst_retrieve = \
        utils.generate_retrieve_binding("NeutronAllNetworks")

    if (all_src not in context.store):
        f.add(RetrieveNeutronNetworks(
            context.src_cloud,
            name=all_src,
            provides=all_src_retrieve
        ))
        context.store[all_src] = None

    if (all_dst not in context.store):
        f.add(RetrieveNeutronNetworks(
            context.dst_cloud,
            name=all_dst,
            provides=all_dst_retrieve
        ))
        context.store[all_dst] = None

    f.add(RetrieveNetworkById(context.src_cloud,
                              name=network_retrieve,
                              provides=network_retrieve,
                              rebind=[
                                  all_src_retrieve,
                                  network_binding,
                              ]))

    f.add(EnsureNetwork(context.dst_cloud,
                        name=network_ensure,
                        provides=network_ensure,
                        rebind=[
                            all_dst_retrieve,
                            network_retrieve,
                            tenant_info
                        ]))

    return f, network_ensure
