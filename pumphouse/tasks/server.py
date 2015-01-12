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
from pumphouse import exceptions
# from pumphouse.tasks import floating_ip as fip_tasks
from pumphouse.tasks.network.nova import floating_ip as fip_tasks
from pumphouse.tasks import image as image_tasks
from pumphouse.tasks import keypair as keypair_tasks
from pumphouse.tasks import snapshot as snapshot_tasks
from pumphouse.tasks import volume as volume_tasks
from pumphouse.tasks import utils as task_utils
from pumphouse import utils
from pumphouse import plugin


LOG = logging.getLogger(__name__)

HYPERVISOR_HOSTNAME_ATTR = "OS-EXT-SRV-ATTR:hypervisor_hostname"

provision_server = flows.register("provision_server", default="image")
network_manager = plugin.Plugin("network", default="nova")


class EvacuateServer(task.BaseCloudTask):
    """Migrates server within the cloud."""

    def __init__(self, cloud, block_migration=True, disk_over_commit=False,
                 *args, **kwargs):
        super(EvacuateServer, self).__init__(cloud, *args, **kwargs)
        self.block_migration = block_migration
        self.disk_over_commit = disk_over_commit

    def execute(self, server_info, **requires):
        server_id = server_info["id"]
        self.evacuation_event(server_info)
        # NOTE(akscram): The destination host will be chosen by the
        #                scheduler.
        self.cloud.nova.servers.live_migrate(server_id, None,
                                             self.block_migration,
                                             self.disk_over_commit)
        server = self.cloud.nova.servers.get(server_id)
        self.evacuation_event(server.to_dict())
        server = utils.wait_for(server.id, self.cloud.nova.servers.get)
        migrated_server_info = server.to_dict()
        self.evacuation_event(migrated_server_info)
        return migrated_server_info

    def evacuation_event(self, server):
        if HYPERVISOR_HOSTNAME_ATTR not in server:
            LOG.warning("Could not get %r attribute from server %r",
                        HYPERVISOR_HOSTNAME_ATTR, server)
            return
        hostname = server[HYPERVISOR_HOSTNAME_ATTR]
        LOG.info("Perform evacuation of server %r from %r host",
                 server["id"], hostname)
        events.emit("update", {
            "id": server["id"],
            "type": "server",
            "cloud": self.cloud.name,
            "action": "",
            "data": dict(server,
                         status=server["status"].lower(),
                         image_id=server["image"]["id"],
                         host_id=hostname),
        }, namespace="/events")


class ServerStartMigrationEvent(task.BaseCloudTask):
    def execute(self, server_id):
        LOG.info("Migration of server %r started", server_id)
        events.emit("update", {
            "id": server_id,
            "cloud": self.cloud.name,
            "type": "server",
            "action": "migration",
        }, namespace="/events")

    def revert(self, server_id, result, flow_failures):
        msg = ("Migration of server {} failed by reason {}"
               .format(server_id, result))
        LOG.warning(msg)
        events.emit("log", {
            "level": "error",
            "message": msg,
        }, namespace="/events")
        events.emit("update", {
            "id": server_id,
            "cloud": self.cloud.name,
            "type": "server",
            "progress": None,
            "action": None,
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
        suspend_server_info = server.to_dict()
        self.suspend_event(suspend_server_info)
        return suspend_server_info

    def suspend_event(self, server):
        LOG.info("Server suspended: %s", server)
        events.emit("update", {
            "id": server["id"],
            "cloud": self.cloud.name,
            "type": "server",
            "data": server,
        }, namespace="/events")

    def revert(self, server_info, result, flow_failures):
        self.cloud.nova.servers.resume(server_info["id"])
        server = utils.wait_for(server_info["id"], self.cloud.nova.servers.get,
                                value="ACTIVE")
        resume_server_info = server.to_dict()
        self.resume_event(resume_server_info)
        return resume_server_info

    def resume_event(self, server):
        LOG.info("Server resumed: %s", server["id"])
        events.emit("update", {
            "id": server["id"],
            "cloud": self.cloud.name,
            "type": "server",
            "data": server,
        }, namespace="/events")


class BootServerFromImage(task.BaseCloudTask):
    def execute(self, server_info, image_info, flavor_info, keypair_info,
                user_info, tenant_info, server_nics, server_dm):
        restrict_cloud = self.cloud.restrict(
            username=user_info["name"],
            tenant_name=tenant_info["name"],
            password="default")
        if keypair_info is not None:
            key_name = keypair_info["name"]
        else:
            key_name = None
        server = restrict_cloud.nova.servers.create(
            server_info["name"], image_info["id"], flavor_info["id"],
            block_device_mapping=dict(server_dm),
            nics=server_nics,
            key_name=key_name)
        server = utils.wait_for(server, self.cloud.nova.servers.get,
                                value="ACTIVE")
        spawn_server_info = server.to_dict()
        for volume_id in dict(server_dm).values():
            volume = self.cloud.cinder.volumes.get(volume_id)
            volume = utils.wait_for(volume.id,
                                    self.cloud.cinder.volumes.get,
                                    value="in-use")
            self.attach_event(volume.id,
                              server.id)
        self.spawn_event(spawn_server_info)
        return spawn_server_info

    def attach_event(self, volume_id, server_id):
        LOG.info("Volume updated: %s", volume_id)
        events.emit("update", {
            "id": volume_id,
            "cloud": self.cloud.name,
            "type": "volume",
            "action": "attach",
            "data": dict(server_ids=[server_id]),
        }, namespace="/events")

    def spawn_event(self, server):
        LOG.info("Server spawned: %s", server)
        if HYPERVISOR_HOSTNAME_ATTR not in server:
            LOG.warning("Could not get %r attribute from server %r",
                        HYPERVISOR_HOSTNAME_ATTR, server)
            return
        hostname = server[HYPERVISOR_HOSTNAME_ATTR]
        events.emit("create", {
            "id": server["id"],
            "cloud": self.cloud.name,
            "type": "server",
            "action": "migration",
            "data": dict(server,
                         image_id=server["image"]["id"],
                         host_id=hostname),
        }, namespace="/events")


class TerminateServer(task.BaseCloudTask):
    def execute(self, server_info):
        self.cloud.nova.servers.delete(server_info["id"])
        self.terminate_event(server_info)

    def detach_event(self, volume_id):
        LOG.info("Volume updated: %s", volume_id)
        events.emit("update", {
            "id": volume_id,
            "cloud": self.cloud.name,
            "type": "volume",
            "action": "detach",
            "data": dict(server_ids=[]),
        }, namespace="/events")

    def terminate_event(self, server):
        LOG.info("Server terminated: %s", server["id"])
        events.emit("delete", {
            "id": server["id"],
            "type": "server",
            "cloud": self.cloud.name,
        }, namespace="/events")
        server_volumes = server.get("os-extended-volumes:volumes_attached",
                                    [])
        for volume in server_volumes:
            self.detach_event(volume["id"])


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
    server_dm = "{}-device-mapping".format(server_binding)

    pre_suspend_tasks, pre_suspend_sync, pre_boot_tasks, image_ensure = \
        provision_server(context, server)

    if server.key_name:
        keypair_ensure = "keypair-{}-ensure".format(server.key_name)
        keypair_flow = keypair_tasks.migrate_keypair(context, None,
                                                     server.tenant_id,
                                                     server.user_id,
                                                     server.key_name)
        if keypair_flow is not None:
            pre_suspend_tasks += [keypair_flow]
    else:
        keypair_ensure = "keypair-server-{}-ensure".format(server_id)
        context.store[keypair_ensure] = None

    migrate_server_volumes = volume_tasks.migrate_server_volumes(
        context,
        server_id,
        getattr(server,
                "os-extended-volumes:volumes_attached"),
        server.user_id,
        server.tenant_id)
    pre_boot_tasks = pre_boot_tasks + [migrate_server_volumes]

    flow = linear_flow.Flow("migrate-server-{}".format(server_id))
    # NOTE(akscram): The synchronization point avoids excessive downtime
    #                of the server.
    flow.add(
        task_utils.SyncPoint(name=server_sync,
                             requires=[flavor_ensure] + pre_suspend_sync),
        ServerStartMigrationEvent(context.src_cloud,
                                  name=server_start_event,
                                  rebind=[server_retrieve]),
        RetrieveServer(context.src_cloud,
                       name=server_binding,
                       provides=server_binding,
                       rebind=[server_retrieve]),
        SuspendServer(context.src_cloud,
                      name=server_suspend,
                      provides=server_suspend,
                      rebind=[server_binding]),
    )
    if pre_boot_tasks:
        flow.add(*pre_boot_tasks)
    flow.add(
        BootServerFromImage(context.dst_cloud,
                            name=server_boot,
                            provides=server_boot,
                            rebind=[server_suspend, image_ensure,
                                    flavor_ensure, keypair_ensure,
                                    user_ensure, tenant_ensure,
                                    server_nics, server_dm]),
    )
    restore_floating_ips = network_manager(context, server.to_dict())
    if restore_floating_ips:
        flow.add(restore_floating_ips)
    flow.add(
        TerminateServer(context.src_cloud,
                        name=server_terminate,
                        rebind=[server_suspend]),
    )
    context.store[server_retrieve] = server_id
    return pre_suspend_tasks, flow


@provision_server.add("image")
def rebuild_by_image(context, server):
    image_id = server.image["id"]
    image_binding = "image-{}".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)

    pre_suspend = []
    if image_binding not in context.store:
        image_flow = image_tasks.migrate_image(context, image_id)
        pre_suspend.append(image_flow)

    return pre_suspend, [image_ensure], [], image_ensure


@provision_server.add("snapshot")
def rebuild_by_snapshot(context, server):
    server_id = server.id
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)

    snapshot_flow = snapshot_tasks.migrate_snapshot(context, server)

    return [], [], [snapshot_flow], snapshot_ensure


@network_manager.add("nova")
def restore_floating_ips_nova(context, server_info):
    flow = unordered_flow.Flow("post-migration-{}".format(server_info["id"]))
    addresses = server_info["addresses"]
    for label in addresses:
        fixed_ips = addresses[label]
        if not fixed_ips:
            continue
        fixed_ip = fixed_ips[0]
        for floating_ip in [addr["addr"] for addr in addresses[label]
                            if addr['OS-EXT-IPS:type'] == 'floating']:
            fip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
            if fip_retrieve in context.store:
                fip_flow = fip_tasks.associate_floating_ip_server(
                    context,
                    floating_ip, fixed_ip,
                    server_info["id"])
                flow.add(fip_flow)
            else:
                raise exceptions.NotFound()
    return flow


@network_manager.add("neutron")
def restore_floating_ips_neutron(context, server_info):
    return None


def evacuate_server(context, flow, hostname, requires=None):
    server_retrieve = "server-{}-retrieve".format(hostname)
    server_binding = "server-{}".format(hostname)
    server_evacuate = "server-{}-evacuate".format(hostname)
    server_evacuated = "server-{}-evacuated".format(hostname)
    flow.add(EvacuateServer(context.src_cloud,
                            name=server_evacuate,
                            provides=server_evacuated,
                            rebind=[server_retrieve],
                            requires=requires or []))
    if server_binding not in context.store:
        context.store[server_binding] = hostname
        flow.add(RetrieveServer(context.src_cloud,
                                name=server_retrieve,
                                provides=server_retrieve,
                                rebind=[server_binding]))
