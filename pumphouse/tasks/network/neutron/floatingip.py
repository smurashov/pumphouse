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

import inspect
import logging

from pumphouse import task
from taskflow.patterns import graph_flow
from . import utils

LOG = logging.getLogger(__name__)


def get_floatingIp_by(neutron, floatingIp_filter):
    try:
        return neutron.list_floatingips(**floatingIp_filter)["floatingips"]
    except Exception as e:
        raise e


def create_floatingip(neutron, floating_info):
    try:
        return neutron.create_floatingip(
            {'floatingip': floating_info}
        )
    except Exception as e:
        raise e


class RetrieveFloatingIps(task.BaseCloudTask):

    def execute(self):
        return get_floatingIp_by(self.cloud.neutron, {})


class RetrieveFloatingIpById(task.BaseCloudTask):

    def execute(self, all_floatingips, floating_id):
        for floating_ip in all_floatingips:
            if (floating_ip['id'] == floating_id):
                return floating_ip

        return None


class EnsureFloatingIp(task.BaseCloudTask):

    def execute(self, all_floatingips, floating_info,
                network_info, port_info, tenant_info):
        # TODO add router_id to arguments
        for floating_ip in all_floatingips:
            if (floating_ip['floating_ip_address'] ==
                    floating_info['floating_ip_address']):
                return floating_ip

        SKIP_PROPS = ["id", "router_id", "floating_ip_address",
                      "status", "tenant_id", "fixed_ip_address"]

        for prop in SKIP_PROPS:
            if prop in floating_info:
                LOG.info("removed prop: %s" % prop)
                del floating_info[prop]

        floating_info["floating_network_id"] = network_info["id"]
        floating_info["port_id"] = port_info["id"]
        floating_info["tenant_id"] = tenant_info["id"]

        return create_floatingip(self.cloud.neutron, floating_info)


def migrate_floatingip(context, floatingip_id, floating_ip_addr,
                       network_info, port_info, tenant_info):

    floatingip_binding = "floating-ip-{}".format(floating_ip_addr)

    floatingip_retrieve = "{}-retrieve".format(
        floatingip_binding)
    floatingip_ensure = "{}-ensure".format(
        floatingip_binding)

    (retrieve, ensure) = utils.generate_binding(
        floatingip_binding, inspect.stack()[0][3])

    if (floatingip_binding in context.store):
        return None, floatingip_retrieve

    context.store[floatingip_retrieve] = floatingip_id

    f = graph_flow.Flow(
        "neutron-floatingip-migration-{}".format(floatingip_binding))

    all_src_floatingips_binding = "srcNeutronAllFloatingIps"
    all_dst_floatingips_binding = "dstNeutronAllFloatingIps"

    if (all_src_floatingips_binding not in context.store):
        f.add(RetrieveFloatingIps(
            context.src_cloud,
            name="retrieveAllSrcFloatingIps",
            provides=all_src_floatingips_binding
        ))
        context.store[all_src_floatingips_binding] = None

    if (all_dst_floatingips_binding not in context.store):
        f.add(RetrieveFloatingIps(
            context.dst_cloud,
            name="retrieveDstAllFloatingIps",
            provides=all_dst_floatingips_binding
        ))
        context.store[all_dst_floatingips_binding] = None

    f.add(RetrieveFloatingIpById(context.src_cloud,
                                 name=floatingip_binding,
                                 provides=floatingip_binding,
                                 rebind=[
                                     all_src_floatingips_binding,
                                     floatingip_retrieve,
                                 ]))

    f.add(EnsureFloatingIp(context.dst_cloud,
                           name=floatingip_ensure,
                           provides=floatingip_ensure,
                           rebind=[
                               all_dst_floatingips_binding,
                               floatingip_binding,
                               network_info,
                               port_info,
                               tenant_info
                           ]))

    return f, floatingip_ensure
