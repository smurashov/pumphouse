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
from pumphouse.tasks import snapshot as snapshot_tasks
from pumphouse.tasks import flavor as flavor_tasks
from pumphouse.tasks import secgroup as secgroup_tasks
from pumphouse.tasks import floating_ip as fip_tasks
from pumphouse.tasks import identity as identity_tasks


LOG = logging.getLogger(__name__)

migrate_disk = flows.register("migrate_disk")
post_hooks = flows.register("post_server")


def migrate_server(src, dst, store, server_id):
    server = src.nova.servers.get(server_id)
    server_id = server.id
    flavor_id = server.flavor["id"]
    flavor_retrieve = "flavor-{}-retrieve".format(flavor_id)
    resources = []
    identity_flow, store = identity_tasks.migrate_server_identity(
        src, dst, store, server.to_dict())
    resources.append(identity_flow)
    tenant = src.keystone.tenants.get(server.tenant_id)
    restrict_src = src.restrict(tenant_name=tenant.name)
    for name in [sg["name"] for sg in server.security_groups]:
        secgroup = restrict_src.nova.security_groups.find(name=name)
        secgroup_retrieve = "secgroup-{}-retrieve".format(secgroup.id)
        if secgroup_retrieve not in store:
            secgroup_flow, store = secgroup_tasks.migrate_secgroup(
                src, dst, store, secgroup.id, tenant.id, server.user_id)
            resources.append(secgroup_flow)
    for floating_ip in [addr["addr"]
                        for addr in server.addresses.values().pop()
                        if addr['OS-EXT-IPS:type'] == 'floating']:
        floating_ip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
        if floating_ip_retrieve not in store:
            floating_ip_flow, store = fip_tasks.migrate_floating_ip(
                src, dst, store, floating_ip)
        resources.append(floating_ip_flow)
    if flavor_retrieve not in store:
        flavor_flow, store = flavor_tasks.migrate_flavor(src, dst, store,
                                                         flavor_id)
        resources.append(flavor_flow)
    migrate_disk_func = migrate_disk.select("image")
    image_ensure, resources, store = migrate_disk_func(src, dst, store,
                                                       resources, server)
    server_flow, store = server_tasks.reprovision_server(src, dst, store,
                                                         server, image_ensure)
    return resources, server_flow, store


@migrate_disk.add("image")
def migrate_disk_with_image(src, dst, store, resources, server):
    image_id = server.image["id"]
    image_retrieve = "image-{}-retrieve".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)
    if image_retrieve not in store:
        image_flow, store = image_tasks.migrate_image(src, dst, store,
                                                      image_id)
        resources.append(image_flow)
    return image_ensure, resources, store


@migrate_disk.add("snapshot")
def migrate_disk_with_snapshot(src, dst, store, resources, server):
    snapshot_retrieve = "snapshot-{}".format(server.id)
    snapshot_ensure = "snapshot-{}-ensure".format(server.id)
    if snapshot_ensure not in store:
        snapshot_flow, store = snapshot_tasks.migrate_snapshot(src, dst, store,
                                                               server.id,
                                                               server.user_id)
        resources.append(snapshot_flow)
    return snapshot_ensure, resources, store
