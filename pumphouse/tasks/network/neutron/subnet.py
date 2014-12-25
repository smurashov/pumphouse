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


def get_subnet_by(neutron, subnet_filter):
    try:
        return neutron.list_subnets(**subnet_filter)['subnets']
    except Exception as e:
        raise e


def create_subnet(neutron, subnet_info):
    try:
        return neutron.create_subnet({'subnet': subnet_info})['subnet']
    except Exception as e:
        raise e


class RetrieveAllSubnets(task.BaseCloudTask):

    def execute(self):
        return get_subnet_by(self.cloud.neutron, {})


class RetrieveSubnetById(task.BaseCloudTask):

    def execute(self, subnets, subnet_id):
        for subnet in subnets:
            if (subnet['id'] == subnet_id):
                return subnet

        return None


class EnsureSubnet(task.BaseCloudTask):

    def execute(self, subnets, subnet_info, network_info, tenant_info):
        for subnet in subnets:
            if (subnet['name'] == subnet_info['name']):
                LOG.info("Subnet %s is allready exists, name: %s" %
                         (subnet_info['id'], subnet_info['name']))
                return subnet

        LOG.info("Subnet not found, name: %s" % subnet_info['name'])

        subnet = create_subnet(self.cloud.neutron, {
            'allocation_pools': subnet_info['allocation_pools'],
            'cidr': subnet_info['cidr'],
            'ip_version': subnet_info['ip_version'],
            'gateway_ip': subnet_info['gateway_ip'],
            'name': subnet_info['name'],
            'network_id': network_info['id'],
            'tenant_id': tenant_info['id']
        })

        LOG.info("Subnet %s created: %s" % (subnet['id'], str(subnet)))

        return subnet


def migrate_subnet(context, subnet_id, network_info, tenant_info):

    subnet_binding = subnet_id

    subnet_retrieve = "subnet-{}-retrieve".format(
        subnet_binding)
    subnet_ensure = "subnet-{}-ensure".format(subnet_binding)

    if (subnet_binding in context.store):
        return None, subnet_ensure

    context.store[subnet_binding] = subnet_id

    f = graph_flow.Flow("neutron-subnet-migration-{}".format(subnet_id))

    all_dst, all_src, all_src_retrieve, all_dst_retrieve = utils.generate_retrieve_binding("NeutronAllSubnets")

    if (all_src not in context.store):

        f.add(RetrieveAllSubnets(
            context.src_cloud,
            name=all_src,
            provides=all_src_retrieve
        ))

        context.store[all_src] = None

    if (all_dst not in context.store):

        f.add(RetrieveAllSubnets(
            context.dst_cloud,
            name=all_dst,
            provides=all_dst_retrieve
        ))

        context.store[all_dst] = None

    f.add(RetrieveSubnetById(context.src_cloud,
                             name=subnet_retrieve,
                             provides=subnet_retrieve,
                             rebind=[
                                 all_src_retrieve,
                                 subnet_binding
                             ]))

    f.add(EnsureSubnet(context.dst_cloud,
                       name=subnet_ensure,
                       provides=subnet_ensure,
                       rebind=[
                           all_dst_retrieve,
                           subnet_retrieve,
                           network_info,
                           tenant_info
                       ]))

    return f, subnet_ensure
