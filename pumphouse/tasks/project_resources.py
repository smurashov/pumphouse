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

from taskflow.patterns import graph_flow

from pumphouse.tasks import server_resources
from pumphouse.tasks import keypair as keypair_tasks
from pumphouse.tasks import image as image_tasks
from pumphouse.tasks import volume as volume_tasks
from pumphouse.tasks import identity as identity_tasks
from pumphouse.tasks import network as network_tasks
from pumphouse.tasks import quota


LOG = logging.getLogger(__name__)


def migrate_project_servers(context, flow, tenant_id):
    servers = context.src_cloud.nova.servers.list(
        search_opts={'all_tenants': 1, 'tenant_id': tenant_id})
    migrate_server = server_resources.migrate_server
    for server in servers:
        server_binding = "server-{}".format(server.id)
        if server_binding not in context.store:
            resources, server_flow = migrate_server(context, server.id)
            flow.add(*resources)
            flow.add(server_flow)


def migrate_project_keypairs(context, flow, tenant_id):
    tenant = context.src_cloud.keystone.tenants.get(tenant_id)
    users = context.src_cloud.keystone.users.list(tenant_id)
    for user in users:
        if user.id == context.src_cloud.keystone.auth_ref.user_id:
            continue
        # XXX(akscram): Works only for users' passowrd which are equal
        #               to "default".
        cloud = context.src_cloud.restrict(username=user.name,
                                           password="default",
                                           tenant_name=tenant.name)
        keypairs = cloud.nova.keypairs.list()
        for keypair in keypairs:
            keypair_tasks.migrate_keypair(context, flow, tenant_id, user.id,
                                          keypair.name)


def migrate_project_images(context, flow, tenant_id):
    images = context.src_cloud.glance.images.list(
        filters={"owner": tenant_id})
    for image in list(images):
        image_binding = "image-{}".format(image.id)
        if image_binding not in context.store:
            image_flow = image_tasks.migrate_image(context, image.id)
            flow.add(image_flow)


def migrate_project_volumes(context, flow, tenant_id):
    volumes = context.src_cloud.cinder.volumes.list(
        search_opts={"all_tenants": 1})
    for volume in volumes:
        volume_tenant_id = getattr(volume, "os-vol-tenant-attr:tenant_id")
        volume_binding = "volume-{}".format(volume.id)
        if volume_binding not in context.store \
                and volume.status == "available" \
                and volume_tenant_id == tenant_id:
            volume_flow = volume_tasks.migrate_detached_volume(
                context, volume.id, None, tenant_id)
            flow.add(volume_flow)


def migrate_project_quota(context, flow, tenant_id):
    endpoints = context.src_cloud.keystone.service_catalog.get_endpoints()
    services = endpoints.keys()
    for service in services:
        if service in quota.SERVICES:
            flow.add(quota.migrate_tenant_quota(context, service, tenant_id))
    return flow


def migrate_project_networks(context, flow, tenant_id):
    networks = context.src_cloud.neutron.list_networks(
        tenant_id=tenant_id)["networks"]
    for network in networks:
        network_id = network["id"]
        network_binding = network_id
        if network_binding not in context.store:
            net_flow, _ = network_tasks.neutron.network.migrate_network(
                network_id, tenant_id)
            flow.add(net_flow)
            _migrate_project_subnets(context, flow,
                                     network_id,
                                     tenant_id)
    return flow


def _migrate_project_subnets(context, flow, network_id, tenant_id):
    subnets = context.src_cloud.neutron.list_subnets(
        network_id=network_id)["subnets"]
    for subnet in subnets:
        subnet_id = subnet["id"]
        subnet_binding = subnet_id
        tenant_ensure = "tenant-{}-ensure".format(tenant_id)
        network_ensure = "network-{}-ensure".format(network_id)
        if subnet_binding not in context.store:
            subnet_flow, _ = network_tasks.neutron.network.migrate_subnet(
                subnet_id, network_ensure, tenant_ensure)
            flow.add(subnet_flow)
    return flow


def migrate_project(context, project_id):
    flow = graph_flow.Flow("migrate-project-{}".format(project_id))
    _, identity_flow = identity_tasks.migrate_identity(context, project_id)
    flow.add(identity_flow)
    migrate_project_servers(context, flow, project_id)
    migrate_project_keypairs(context, flow, project_id)
    migrate_project_images(context, flow, project_id)
    migrate_project_volumes(context, flow, project_id)
    migrate_project_quota(context, flow, project_id)
    return flow
