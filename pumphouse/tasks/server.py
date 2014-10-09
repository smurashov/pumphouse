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

from taskflow.patterns import linear_flow, unordered_flow

from pumphouse import events
from pumphouse import flows
from pumphouse import task
from pumphouse.tasks import floating_ip as fip_tasks
from pumphouse.tasks import image as image_tasks
from pumphouse.tasks import snapshot as snapshot_tasks
from pumphouse.tasks import utils as task_utils
from pumphouse import utils


LOG = logging.getLogger(__name__)

HYPERVISOR_HOSTNAME_ATTR = "OS-EXT-SRV-ATTR:hypervisor_hostname"

provision_server = flows.register("provision_server", default="image")


class EvacuateServer(task.BaseCloudTask):
    """Migrates server within the cloud."""

    def __init__(self, block_migration=True, disk_over_commit=False,
                 *args, **kwargs):
        super(EvacuateServer, self).__init__(*args, **kwargs)
        self.block_migration = block_migration
        self.disk_over_commit = disk_over_commit

    def execute(self, server_info, hostname):
        server_id = server_info["id"]
        self.evacuation_start_event(server_info)
        self.cloud.nova.servers.live_migrate(server_id, hostname,
                                             self.block_migration,
                                             self.disk_over_commit)
        server = utils.wait_for(server_id, self.cloud.nova.servers.get)
        server = server.to_dict()
        self.evacuation_end_event(server)
        return server

    def evacuation_start_event(self, server):
        server_id = server["id"]
        try:
            hostname = server[HYPERVISOR_HOSTNAME_ATTR]
        except KeyError:
            LOG.warning("Could not get %r attribute from server %r: %s",
                        HYPERVISOR_HOSTNAME_ATTR, server_id)
        else:
            LOG.info("Perform evacuation of server %r from $r host",
                     server_id, hostname)
            events.emit("server evacuate", {
                "id": server_id,
                "cloud": self.cloud.name,
            }, namespace="/events")

    def evacuation_end_event(self, server):
        server_id = server["id"]
        try:
            hostname = server[HYPERVISOR_HOSTNAME_ATTR]
        except KeyError:
            LOG.warning("Could not get %r attribute from server %r: %s",
                        HYPERVISOR_HOSTNAME_ATTR, server_id)
        else:
            LOG.info("Server %r evacuated to host %r", server_id, hostname)
            events.emit("server evacuated", {
                "id": server_id,
                "host_name": hostname,
                "cloud": self.cloud.name,
            }, namespace="/events")


class ServerStartMigrationEvent(task.BaseCloudTask):
    def execute(self, server_id):
        LOG.info("Migration of server %r started", server_id)
        events.emit("server migrate", {
            "id": server_id,
        }, namespace="/events")

    # TODO(akscram): Here we can emit the event to report about
    #                failures during migration process. It's commented
    #                because didn't supported by UI and untested.
#    def revert(self, server_id, result, flow_failures):
#        LOG.info("Migration of server %r failed by reason %s",
#                 server_id, result)
#        events.emit("server migration failed", {
#            "id": server_id,
#        }, namespace="/events")


class ServerSuccessMigrationEvent(task.BaseCloudsTask):
    def execute(self, src_server_info, dst_server_info):
        events.emit("server migrated", {
            "source_id": src_server_info["id"],
            "destination_id": dst_server_info["id"],
        }, namespace="/events")


class RetrieveServer(task.BaseCloudTask):
    def execute(self, server_id):
        server = self.cloud.nova.servers.get(server_id)
        return server.to_dict()


class SuspendServer(task.BaseCloudTask):
    def execute(self, server_info):
        self.cloud.nova.servers.suspend(server_info["id"])
        server = utils.wait_for(server_info["id"], self.cloud.nova.servers.get,
                                value="SUSPENDED")
        self.suspend_event(server)
        return server.to_dict()

    def suspend_event(self, server):
        LOG.info("Server suspended: %s", server.id)
        events.emit("server suspended", {
            "id": server.id,
            "cloud": self.cloud.name,
        }, namespace="/events")

    def revert(self, server_info, result, flow_failures):
        self.cloud.nova.servers.resume(server_info["id"])
        server = utils.wait_for(server_info["id"], self.cloud.nova.servers.get,
                                value="ACTIVE")
        self.resume_event(server)
        return server.to_dict()

    def resume_event(self, server):
        LOG.info("Server resumed: %s", server.id)
        events.emit("server resumed", {
            "id": server.id,
            "cloud": self.cloud.name,
        }, namespace="/events")


class BootServerFromImage(task.BaseCloudTask):
    def execute(self, server_info, image_info, flavor_info, user_info,
                tenant_info, server_nics):
        # TODO(akscram): Network information doesn't saved.
        restrict_cloud = self.cloud.restrict(
            username=user_info["name"],
            tenant_name=tenant_info["name"],
            password="default")
        server = restrict_cloud.nova.servers.create(server_info["name"],
                                                    image_info["id"],
                                                    flavor_info["id"],
                                                    nics=server_nics)
        server = utils.wait_for(server, self.cloud.nova.servers.get,
                                value="ACTIVE")
        self.spawn_event(server)
        return server.to_dict()

    def spawn_event(self, server):
        LOG.info("Server spawned: %s", server.id)
        try:
            hostname = getattr(server, HYPERVISOR_HOSTNAME_ATTR)
        except AttributeError as err:
            LOG.warning("Could not get %r attribute from server %r: %s",
                        HYPERVISOR_HOSTNAME_ATTR, server.id, err)
        else:
            events.emit("server boot", {
                "cloud": self.cloud.name,
                "id": server.id,
                "name": server.name,
                "tenant_id": server.tenant_id,
                "image_id": server.image["id"],
                "host_name": hostname,
                "status": "active",
            }, namespace="/events")


class TerminateServer(task.BaseCloudTask):
    def execute(self, server_info):
        self.cloud.nova.servers.delete(server_info["id"])
        self.terminate_event(server_info)

    def terminate_event(self, server):
        LOG.info("Server terminated: %s", server["id"])
        events.emit("server terminate", {
            "cloud": self.cloud.name,
            "id": server["id"],
        }, namespace="/events")


def reprovision_server(context, server, server_nics):
    flavor_ensure = "flavor-{}-ensure".format(server.flavor["id"])
    user_ensure = "user-{}-ensure".format(server.user_id)
    tenant_ensure = "tenant-{}-ensure".format(server.tenant_id)

    server_id = server.id
    server_start_event = "server-{}-start-event".format(server_id)
    server_finish_event = "server-{}-finish-event".format(server_id)
    server_binding = "server-{}".format(server_id)
    server_retrieve = "server-{}-retrieve".format(server_id)
    server_suspend = "server-{}-suspend".format(server_id)
    server_terminate = "server-{}-terminate".format(server_id)
    server_boot = "server-{}-boot".format(server_id)
    server_sync = "server-{}-sync".format(server_id)

    pre_suspend_tasks, pre_suspend_sync, pre_boot_tasks, image_ensure = \
        provision_server(context, server)

    flow = linear_flow.Flow("migrate-server-{}".format(server_id))
    # NOTE(akscram): The synchronization point avoids excessive downtime
    #                of the server.
    flow.add(
        task_utils.SyncPoint(name=server_sync,
                             requires=[flavor_ensure] + pre_suspend_sync),
        ServerStartMigrationEvent(context.src_cloud,
                                  name=server_start_event,
                                  rebind=[server_binding]),
        RetrieveServer(context.src_cloud,
                       name=server_binding,
                       provides=server_retrieve,
                       rebind=[server_binding]),
        SuspendServer(context.src_cloud,
                      name=server_retrieve,
                      provides=server_suspend,
                      rebind=[server_retrieve]),
    )
    if pre_boot_tasks:
        flow.add(*pre_boot_tasks)
    flow.add(
        BootServerFromImage(context.dst_cloud,
                            name=server_boot,
                            provides=server_boot,
                            rebind=[server_suspend, image_ensure,
                                    flavor_ensure, user_ensure,
                                    tenant_ensure, server_nics]),
        restore_floating_ips(context, server.to_dict()),
        TerminateServer(context.src_cloud,
                        name=server_terminate,
                        rebind=[server_suspend]),
        ServerSuccessMigrationEvent(context.src_cloud, context.dst_cloud,
                                    name=server_finish_event,
                                    rebind=[server_retrieve, server_boot]),
    )
    context.store[server_binding] = server_id
    return pre_suspend_tasks, flow


@provision_server.add("image")
def rebuild_by_image(context, server):
    image_id = server.image["id"]
    image_retrieve = "image-{}-retrieve".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)

    pre_suspend = []
    if image_retrieve not in context.store:
        image_flow = image_tasks.migrate_image(context, image_id)
        pre_suspend.append(image_flow)

    return pre_suspend, [image_ensure], [], image_ensure


@provision_server.add("snapshot")
def rebuild_by_snapshot(context, server):
    server_id = server.id
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)

    snapshot_flow = snapshot_tasks.migrate_snapshot(context, server)

    return [], [], [snapshot_flow], snapshot_ensure


def restore_floating_ips(context, server_info):
    flow = unordered_flow.Flow("post-migration-{}".format(server_info["id"]))
    addresses = server_info["addresses"]
    for label in addresses:
        fixed_ip = addresses[label][0]
        for floating_ip in [addr["addr"] for addr in addresses[label]
                            if addr['OS-EXT-IPS:type'] == 'floating']:
            fip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
            if fip_retrieve not in context.store:
                fip_flow = fip_tasks.associate_floating_ip_server(
                    context,
                    floating_ip, fixed_ip,
                    server_info["id"])
                flow.add(fip_flow)
    return flow


def evacuate_server(context, server_id):
    server_retrieve = "server-{}-retrieve".format(server_id)
    server_binding = "server-{}".format(server_id)
    server_evacuate = "server-{}-evacuate".format(server_id)
    server_evacuated = "server-{}-evacuated".format(server_id)
    if server_evacuated not in context.store:
        evacuate = EvacuateServer(context.src_cloud,
                                  name=server_evacuate,
                                  requires=server_retrieve,
                                  provides=server_evacuated)
        flow = linear_flow.Flow("evacuate-server-{}".format(server_id))
        if server_retrieve not in context.store:
            flow.add(RetrieveServer(context.src_cloud,
                                    name=server_binding,
                                    provides=server_retrieve,
                                    rebind=[server_binding]))
            flow.add(evacuate)
            return flow
        return evacuate
    return None
