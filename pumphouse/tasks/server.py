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
from pumphouse import task
from pumphouse import flows
from pumphouse.tasks import utils as task_utils
from pumphouse.tasks import floating_ip as fip_tasks
from pumphouse import utils


LOG = logging.getLogger(__name__)

provision_server = flows.register("provision_server")


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
            hostname = getattr(server, "OS-EXT-SRV-ATTR:hypervisor_hostname")
        except AttributeError as err:
            LOG.warning("Could not get 'hypervisor_hostname' attribute from "
                        "server %r: %s", server.id, err)
        else:
            events.emit("server boot", {
                "cloud": self.cloud.name,
                "id": server.id,
                "name": server.name,
                "tenant_id": server.tenant_id,
                # XXX(akscram): It may suitable only for images
                #               (untested for snapshots)
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


def reprovision_server(src, dst, store, server, image_ensure):
    server_id = server.id
    user_id, tenant_id = server.user_id, server.tenant_id
    image_id, flavor_id = server.image["id"], server.flavor["id"]
    server_start_event = "server-{}-start-event".format(server_id)
    server_finish_event = "server-{}-finish-event".format(server_id)
    server_sync = "server-{}-sync".format(server_id)
    server_binding = "server-{}".format(server_id)
    server_retrieve = "server-{}-retrieve".format(server_id)
    server_suspend = "server-{}-suspend".format(server_id)
    server_boot = "server-{}-boot".format(server_id)
    server_terminate = "server-{}-terminate".format(server_id)
    server_nics = "server-{}-nics".format(server_id)
    flavor_ensure = "flavor-{}-ensure".format(flavor_id)
    user_ensure = "user-{}-ensure".format(user_id)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    flow = linear_flow.Flow("migrate-server-{}".format(server_id))
    flow.add(task_utils.SyncPoint(name=server_sync,
                                  requires=[image_ensure, flavor_ensure]))
    flow.add(ServerStartMigrationEvent(src,
                                       name=server_start_event,
                                       rebind=[server_binding]))
    flow.add(RetrieveServer(src,
                            name=server_binding,
                            provides=server_retrieve,
                            rebind=[server_binding]))
    flow.add(SuspendServer(src,
                           name=server_retrieve,
                           provides=server_suspend,
                           rebind=[server_retrieve]))
    flow.add(BootServerFromImage(dst,
                                 name=server_boot,
                                 provides=server_boot,
                                 rebind=[server_suspend, image_ensure,
                                         flavor_ensure, user_ensure,
                                         tenant_ensure, server_nics]
                                 ))
    floating_ips_flow, store = restore_floating_ips(src, dst, store,
                                                    server.to_dict())
    flow.add(floating_ips_flow)
    flow.add(TerminateServer(src,
                             name=server_terminate,
                             rebind=[server_suspend]))
    flow.add(ServerSuccessMigrationEvent(src, dst,
                                         name=server_finish_event,
                                         rebind=[server_retrieve,
                                                 server_boot]))
    store[server_binding] = server_id
    return (flow, store)


def restore_floating_ips(src, dst, store, server_info):
    flow = unordered_flow.Flow("post-migration-{}".format(server_info["id"]))
    addresses = server_info["addresses"]
    for label in addresses:
        fixed_ip = addresses[label][0]
        for floating_ip in [addr["addr"] for addr in addresses[label]
                            if addr['OS-EXT-IPS:type'] == 'floating']:
            fip_retrieve = "floating-ip-{}-retrieve".format(floating_ip)
            if fip_retrieve not in store:
                fip_flow, store = fip_tasks.associate_floating_ip_server(
                    src, dst, store,
                    floating_ip, fixed_ip,
                    server_info["id"])
                flow.add(fip_flow)
    return flow, store
