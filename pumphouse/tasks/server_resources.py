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


LOG = logging.getLogger(__name__)

migrate_server = flows.register("server")
post_hooks = flows.register("post_server")


@migrate_server.add("image")
def migrate_server_with_image(src, dst,
                              restricted_src, restricted_dst,
                              store, server_id):
    server = src.nova.servers.get(server_id)
    image_id, flavor_id = server.image["id"], server.flavor["id"]
    tenant_id, user_id = server.tenant_id, server.user_id
    flavor_retrieve = "flavor-{}-retrieve".format(flavor_id)
    image_retrieve = "image-{}-retrieve".format(image_id)
    resources = []
    for name in [sg["name"] for sg in server.security_groups]:
        secgroup = src.nova.security_groups.find(name=name)
        secgroup_retrieve = "secgroup-{}-retrieve".format(secgroup.id)
        if secgroup_retrieve not in store:
            secgroup_flow, store = secgroup_tasks.migrate_secgroup(
                restricted_src, restricted_dst, store, secgroup.id)
            resources.append(secgroup_flow)
    for floating_ip in [addr["addr"]
                        for addr in server.addresses.values().pop()
                        if addr['OS-EXT-IPS:type'] == 'floating']:
        floating_ip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
        if floating_ip_retrieve not in store:
            floating_ip_flow, store = fip_tasks.migrate_floating_ip(
                src, dst, store, floating_ip)
        resources.append(floating_ip_flow)
    if image_retrieve not in store:
        image_flow, store = image_tasks.migrate_image(src, restricted_dst,
                                                      store,
                                                      image_id)
        resources.append(image_flow)
    if flavor_retrieve not in store:
        flavor_flow, store = flavor_tasks.migrate_flavor(src, dst, store,
                                                         flavor_id)
        resources.append(flavor_flow)
    server_flow, store = server_tasks.reprovision_server_with_image(
        src, restricted_dst, store, server)
    return resources, server_flow, store


@migrate_server.add("snapshot")
def migrate_server_with_snapshot(src, dst,
                                 restricted_src, restricted_dst,
                                 store, server_id):
    server = src.nova.servers.get(server_id)
    flavor_id = server.flavor["id"]
    flavor_retrieve = "flavor-{}-retrieve".format(flavor_id)
    snapshot_retrieve = "snapshot-{}".format(server_id)
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)
    resources = []
    if flavor_retrieve not in store:
        flavor_flow, store = flavor_tasks.migrate_flavor(src, dst, store,
                                                         flavor_id)
        resources.append(flavor_flow)
    for name in [sg["name"] for sg in server.security_groups]:
        secgroup = src.nova.security_groups.find(name=name)
        secgroup_retrieve = "secgroup-{}-retrieve".format(secgroup.id)
        if secgroup_retrieve not in store:
            secgroup_flow, store = secgroup_tasks.migrate_secgroup(
                restricted_src, restricted_dst, store, secgroup.id)
            resources.append(secgroup_flow)
    for floating_ip in [addr["addr"]
                        for addr in server.addresses.values().pop()
                        if addr['OS-EXT-IPS:type'] == 'floating']:
        floating_ip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
        if floating_ip_retrieve not in store:
            floating_ip_flow, store = fip_tasks.migrate_floating_ip(
                src, dst, store, floating_ip)
        resources.append(floating_ip_flow)
    if snapshot_ensure not in store:
        snapshot_flow, store = snapshot_tasks.migrate_snapshot(
            src, restricted_dst, store, server_id)
        resources.append(snapshot_flow)
    server_flow, store = server_tasks.reprovision_server_with_snapshot(
        src, restricted_dst, store, server)
    return resources, server_flow, store
