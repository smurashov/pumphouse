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


LOG = logging.getLogger(__name__)

migrate_server = flows.register("server")


@migrate_server.add("image")
def migrate_server_through_image(src, dst, store, server_id):
    server = src.nova.servers.get(server_id)
    image_id, flavor_id = server.image["id"], server.flavor["id"]
    image_retrieve = "image-{}-retrieve".format(image_id)
    flavor_retrieve = "flavor-{}-retrieve".format(flavor_id)
    resources = []
    if image_retrieve not in store:
        image_flow, store = image_tasks.migrate_image(src, dst, store,
                                                      image_id)
        resources.append(image_flow)
    if flavor_retrieve not in store:
        flavor_flow, store = flavor_tasks.migrate_flavor(src, dst, store,
                                                         flavor_id)
        resources.append(flavor_flow)
    server_flow, store = server_tasks.reprovision_server(src, dst, store,
                                                         server.id,
                                                         image_id,
                                                         flavor_id)
    return resources, server_flow, store


@migrate_server.add("snapshot")
def migrate_server_with_snapshot(src, dst, store, server_id):
    server = src.nova.servers.get(server_id)
    flavor_id = server.flavor["id"]
    snapshot_retrieve = "snapshot-{}".format(server_id)
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)
    flavor_retrieve = "flavor-{}-retrieve".format(flavor_id)
    resources = []
    if snapshot_ensure not in store:
        snapshot_flow, store = snapshot_tasks.migrate_snapshot(src, dst, store,
                                                               server_id)
        resources.append(snapshot_flow)
    if flavor_retrieve not in store:
        flavor_flow, store = flavor_tasks.migrate_flavor(src, dst, store,
                                                         flavor_id)
        resources.append(flavor_flow)
    server_flow, store = server_tasks.reprovision_server_with_snapshot(
        src, dst, store, server.id, flavor_id)
    return resources, server_flow, store
