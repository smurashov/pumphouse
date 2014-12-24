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
from pumphouse.tasks import server as server_tasks
from pumphouse.tasks import flavor as flavor_tasks
from pumphouse.tasks import secgroup as secgroup_tasks
from pumphouse.tasks import network as network_tasks
from pumphouse.tasks import identity as identity_tasks
from pumphouse.tasks import utils as task_utils


LOG = logging.getLogger(__name__)

migrate_disk = flows.register("migrate_disk")
post_hooks = flows.register("post_server")


def migrate_server(context, server_id):
    server = context.src_cloud.nova.servers.get(server_id)
    server_id = server.id
    flavor_id = server.flavor["id"]
    flavor_retrieve = "flavor-{}-retrieve".format(flavor_id)
    resources = []
    identity_flow = identity_tasks.migrate_server_identity(
        context, server.to_dict())
    resources.append(identity_flow)
    tenant = context.src_cloud.keystone.tenants.get(server.tenant_id)
    server_secgroups = server.list_security_group()
    for secgroup in server_secgroups:
        secgroup_retrieve = "secgroup-{}-retrieve".format(secgroup.id)
        if secgroup_retrieve not in context.store:
            secgroup_flow = secgroup_tasks.migrate_secgroup(
                context, secgroup.id, tenant.id, server.user_id)
            resources.append(secgroup_flow)
    server_nics = "server-{}-nics".format(server_id)
    nics = []
    for network_name, addresses in server.addresses.iteritems():
        for address in addresses:
            flow, nic = network_tasks.migrate_nic(
                context, network_name, address, tenant.id, server.user_id)
            if flow is not None:
                resources.append(flow)
            if nic is not None:
                nics.append(nic)
    resources.append(task_utils.Gather(name=server_nics,
                                       provides=server_nics,
                                       rebind=nics))
    if flavor_retrieve not in context.store:
        flavor_flow = flavor_tasks.migrate_flavor(context, flavor_id)
        resources.append(flavor_flow)
    add_resources, server_flow = server_tasks.reprovision_server(
        context, server, server_nics)
    resources += add_resources
    return resources, server_flow
