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

from . import network
from . import subnet
from . import floatingip
from . import router
from . import securitygroup

LOG = logging.getLogger(__name__)


def get_port_by(neutron, port_filter):
    try:
        return neutron.list_ports(**port_filter)['ports']
    except Exception as e:
        raise


def create_port(neutron, port_info):
    try:
        return neutron.create_port(body={'port': port_info})['port']
    except Exception as e:
        raise e


class RetrieveAllPorts(task.BaseCloudTask):

    def execute(self):
        return self.cloud.neutron.list_ports()['ports']


class RetrievePortById(task.BaseCloudTask):

    def execute(self, all_ports, port_id):
        for port in all_ports:
            if port["id"] == port_id:
                LOG.info("port found %s " % str(port))
                return port

        return None


class EnsurePort(task.BaseCloudTask):

    def execute(self, all_ports, port_info, network_info, subnet_info,
                device_info, tenant_info):
        for port in all_ports:
            if (port['mac_address'] == port_info['mac_address']):
                return port

        SKIP_PROPS = ['device_id', 'id', 'security_groups', 'fixed_ips',
                      'status', 'binding:vif_details', 'binding:vif_type']

        for prop in SKIP_PROPS:
            if prop in port_info:
                LOG.info("removed prop: %s" % prop)
                del port_info[prop]

        port_info['network_id'] = network_info['id']
        port_info['tenant_id'] = tenant_info['id']

        port = create_port(self.cloud.neutron, port_info)

        return port


def migrate_port(context, port_id, tenant_binding, user_binding):

    port_binding = port_id

    if (port_binding in context.store):
        return None

    context.store[port_binding] = port_id

    f = graph_flow.Flow("neutron-port-migration-{}".format(port_binding))

    port_info = get_port_by(context.src_cloud.neutron, {'id': port_id})[0]

    all_src_ports_binding = "srcNeutronAllPorts"
    all_dst_ports_binding = "dstNeutronAllPorts"

    if (all_src_ports_binding not in context.store):
        f.add(RetrieveAllPorts(
            context.src_cloud,
            name="retrieveNeutronAllSrcPorts",
            provides=all_src_ports_binding
        ))
        context.store[all_src_ports_binding] = None

    if (all_dst_ports_binding not in context.store):
        f.add(RetrieveAllPorts(
            context.dst_cloud,
            name="retrieveNeutronAllDstPorts",
            provides=all_dst_ports_binding
        ))
        context.store[all_dst_ports_binding] = None

    port_retrieve = "neutron-port-migration-{}-retrieve".format(port_binding)
    port_ensure = "neutron-port-migration-{}-ensure".format(port_binding)
    network_info = "NullNetworkInfo"
    subnet_info = "NullSubnet"
    device_info = "NullDevice"

    if ('network_id' in port_info and port_info['network_id'] is not None):
        networkFlow, network_info = network.migrate_network(
            context, port_info['network_id'], tenant_binding, user_binding)
        if (networkFlow is not None):
            f.add(networkFlow)

    # migrate subnet
    if ('fixed_ips' in port_info and port_info['fixed_ips'] is not None):
        for fixed_ip in port_info['fixed_ips']:
            if 'subnet_id' in fixed_ip:
                subnetFlow, subnet_info = subnet.migrate_subnet(
                    context, fixed_ip['subnet_id'], network_info, tenant_binding)
                if (subnetFlow is not None):
                    f.add(subnetFlow)

    if ("device_owner" in port_info):
        if (port_info['device_owner'] == 'network:floatingip'):
            pass
        elif (port_info["device_owner"] == "network:dhcp"):
            pass
        elif (port_info["device_owner"] == "network:router_gateway"):
            pass
        elif (port_info['device_owner'] == 'compute:None'):
            pass
        elif (port_info["device_owner"] == "network:router_interface"):
            routerFlow, device_info = router.migrate_router(
                context, port_info['device_id'])
            if (routerFlow is not None):
                f.add(routerFlow)

        else:
            raise NotImplementedError("port %s have unknown \
                device_owner %s" % (port_info["id"],
                                    port_info["device_owner"]))

    f.add(RetrievePortById(
        context.src_cloud,
        name=port_retrieve,
        provides=port_retrieve,
        rebind=[all_src_ports_binding, port_binding]
    ))

    context.store[device_info] = None

    f.add(EnsurePort(
        context.dst_cloud,
        name=port_ensure,
        provides=port_ensure,
        rebind=[
            all_dst_ports_binding,
            port_retrieve,
            network_info,
            subnet_info,
            device_info,
            tenant_binding
        ]))

    if (port_info['device_owner'] == 'network:floatingip'):
        floatingIpAddr = floatingip.get_floatingIp_by(
            context.src_cloud.neutron,
            {'id': port_info['device_id']})[0]['floating_ip_address']

        floatingIpFlow, device_info = floatingip.migrate_floatingip(
            context, port_info['device_id'], floatingIpAddr,
            network_info, port_ensure, tenant_binding)
        if (floatingIpFlow is not None):
            f.add(floatingIpFlow)

    if "security_groups" in port_info:
        for security_id in port_info["security_groups"]:
            securityGroupFlow, securityGroup_retrieve = \
                securitygroup.migrate_securityGroup(context,
                                                    security_id, port_ensure)
            if (securityGroupFlow is not None):
                f.add(securityGroupFlow)

    return f, port_ensure


def migrate_nic(context, network_name, address, tenant_id, user_id):

    port_info = context.src_cloud.neutron.list_ports(
        fixed_ips=['ip_address=%s' % address['addr']])['ports'][0]

    tenant_binding = "tenant-{}-ensure".format(tenant_id)
    user_binding = "user-{}-ensure".format(user_id)

    return migrate_port(context, port_info['id'], tenant_binding, user_binding)
