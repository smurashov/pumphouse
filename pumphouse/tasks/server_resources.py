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
from pumphouse.tasks import image as image_tasks
from pumphouse.tasks import flavor as flavor_tasks
from pumphouse.tasks import secgroup as secgroup_tasks
from pumphouse.tasks import floating_ip as fip_tasks
from pumphouse.tasks import identity as identity_tasks


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
    restrict_src = context.src_cloud.restrict(tenant_name=tenant.name)
    for name in [sg["name"] for sg in server.security_groups]:
        secgroup = restrict_src.nova.security_groups.find(name=name)
        secgroup_retrieve = "secgroup-{}-retrieve".format(secgroup.id)
        if secgroup_retrieve not in context.store:
            secgroup_flow = secgroup_tasks.migrate_secgroup(
                context, secgroup.id, tenant.id, server.user_id)
            resources.append(secgroup_flow)
    for floating_ip in [addr["addr"]
                        for addr in server.addresses.values().pop()
                        if addr['OS-EXT-IPS:type'] == 'floating']:
        floating_ip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
        if floating_ip_retrieve not in context.store:
            floating_ip_flow = fip_tasks.migrate_floating_ip(
                context, floating_ip)
        resources.append(floating_ip_flow)
    if flavor_retrieve not in context.store:
        flavor_flow = flavor_tasks.migrate_flavor(context, flavor_id)
        resources.append(flavor_flow)
    if context.config.get("provision_server") == "image":
        migrate_bootable_image(context, resources, server)
    server_flow = server_tasks.reprovision_server(context, server)
    return resources, server_flow


def migrate_bootable_image(context, resources, server):
    image_id = server.image["id"]
    image_retrieve = "image-{}-retrieve".format(image_id)
    if image_retrieve not in context.store:
        image_flow = image_tasks.migrate_image(context, image_id)
        resources.append(image_flow)
