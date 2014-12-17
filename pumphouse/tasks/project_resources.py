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

from taskflow.patterns import graph_flow, unordered_flow

from pumphouse.tasks import server_resources
from pumphouse.tasks import image as image_tasks
from pumphouse.tasks import volume as volume_tasks


LOG = logging.getLogger(__name__)


def migrate_project_servers(context, tenant_id):
    servers = context.src_cloud.nova.servers.list(
        search_opts={'all_tenants': 1, 'tenant_id': tenant_id})
    flow = graph_flow.Flow("migrate-resources-{}".format(tenant_id))
    servers_flow = unordered_flow.Flow("migrate-servers-{}".format(tenant_id))
    migrate_server = server_resources.migrate_server
    for server in servers:
        server_binding = "server-{}".format(server.id)
        if server_binding not in context.store:
            resources, server_flow = migrate_server(context, server.id)
            flow.add(*resources)
            servers_flow.add(server_flow)
    flow.add(servers_flow)
    return flow


def migrate_project_images(context, tenant_id):
    images = context.src_cloud.glance.images.list(owner=tenant_id)
    flow = unordered_flow.Flow("migrate-project-{}-images".format(tenant_id))
    for image in list(images):
        image_binding = "image-{}".format(image.id)
        if image_binding not in context.store:
            image_flow = image_tasks.migrate_image(context, image.id)
            flow.add(image_flow)
    return flow


def migrate_project_volumes(context, tenant_id):
    volumes = context.src_cloud.cinder.volumes.list(
        search_opts={"all_tenants": 1})
    flow = unordered_flow.Flow("migrate-project-{}-volumes".format(tenant_id))
    for volume in volumes:
        tenant_id = getattr(volume, "os-vol-tenant-attr:tenant_id")
        volume_binding = "volume-{}".format(volume.id)
        if volume_binding not in context.store \
                and volume.status == "available":
            volume_flow = volume_tasks.migrate_detached_volume(
                context, volume.id, None, tenant_id)
            flow.add(volume_flow)
    return flow


def migrate_project(context, project_id):
    flow = graph_flow.Flow("migrate-project-{}".format(project_id))
    server_flow = migrate_project_servers(context, project_id)
    images_flow = migrate_project_images(context, project_id)
    volumes_flow = migrate_project_volumes(context, project_id)
    flow.add(server_flow,
             images_flow,
             volumes_flow)
    return flow
