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

from taskflow.patterns import linear_flow

from pumphouse import task
from pumphouse import events
from pumphouse import exceptions
from pumphouse.tasks import utils as task_utils


LOG = logging.getLogger(__name__)


class RetrieveFloatingIP(task.BaseCloudTask):
    def execute(self, address):
        floating_ip = self.cloud.nova.floating_ips_bulk.find(address=address)
        return floating_ip.to_dict()


class EnsureFloatingIPBulk(task.BaseCloudTask):
    def execute(self, floating_ip_info):
        address = floating_ip_info["address"]
        pool = floating_ip_info["pool"]
        try:
            floating_ip = self.cloud.nova.floating_ips_bulk.find(
                address=address)
        except exceptions.nova_excs.NotFound:
            self.cloud.nova.floating_ips_bulk.create(address,
                                                     pool=pool)
            try:
                floating_ip = self.cloud.nova.floating_ips_bulk.find(
                    address=address)
            except exceptions.nova_excs.NotFound:
                LOG.exception("Not added: %s", address)
                self.not_added_event(address)
                raise
            else:
                LOG.info("Created: %s", floating_ip.to_dict())
                self.created_event(floating_ip)
        else:
            LOG.warn("Already exists, %s", floating_ip.to_dict())
        return floating_ip.to_dict()

    def created_event(self, floating_ip):
        events.emit("create", {
            "id": floating_ip.address,
            "type": "floating_ip",
            "cloud": self.cloud.name,
            "data": dict(floating_ip.to_dict(),
                         name=floating_ip.address),
        }, namespace="/events")

    def not_added_event(self, address):
        events.emit("log", {
            "level": "error",
            "message": "FloatingIpsBulk {} was not created, next attempt"
                       .format(address),
        }, namespace="/events")


class EnsureFloatingIP(task.BaseCloudTask):
    # TODO(ogelbukh): this task must be refactored in a way that replaces a
    # while loop with built-in retry mechanism of Taskflow lib
    def execute(self, server_info, floating_ip_info, fixed_ip_info):
        floating_ip_address = floating_ip_info["address"]
        fixed_ip_address = fixed_ip_info["v4-fixed-ip"]
        server_id = server_info["id"]
        try:
            floating_ip = self.cloud.nova.floating_ips_bulk.find(
                address=floating_ip_address)
        except exceptions.nova_excs.NotFound:
            LOG.exception("No Floating IP: %s",
                          floating_ip_address)
            raise
        if floating_ip.instance_uuid is None:
            tries = []
            while len(tries) in range(30):
                try:
                    # FIXME(ogelbukh): pass fixed ip address to bind to,
                    # requires retention of network information for server
                    self.cloud.nova.servers.add_floating_ip(
                        server_id, floating_ip_address, None)
                except exceptions.nova_excs.BadRequest as exc:
                    tries.append(exc)
                    pass
                else:
                    floating_ip = self.cloud.nova.floating_ips_bulk.find(
                        address=floating_ip_address)
                    LOG.info("Assigned floating ip: %s",
                             floating_ip.to_dict())
                    self.assigned_event(floating_ip_address, server_id)
                    return floating_ip.to_dict()
            else:
                LOG.exception("Unable to add floating ip: %s",
                              floating_ip.to_dict())
                self.assigning_error_event(floating_ip_address, server_id)
                raise exceptions.TimeoutException()
        elif floating_ip.instance_uuid == server_id:
            LOG.warn("Already associated: %s", floating_ip)
            return floating_ip.to_dict()
        else:
            LOG.exception("Duplicate association: %s", floating_ip)
            raise exceptions.Conflict()

    def assigned_event(self, address, server_id):
        events.emit("update", {
            "id": address,
            "type": "floating_ip",
            "cloud": self.cloud.name,
            "data": {
                "server_id": server_id,
            }
        }, namespace="/events")

    def assigning_error_event(self, address, server_id):
        events.emit("log", {
            "level": "error",
            "message": "Couldn't assign FloatingIp {} to Server {}"
                       .format(address, server_id),
        }, namespace="/events")


def migrate_floating_ip(context, address):
    """Replicate Floating IP from source cloud to destination cloud"""
    floating_ip_binding = "floating-ip-{}".format(address)
    floating_ip_retrieve = "floating-ip-{}-retrieve".format(address)
    floating_ip_bulk_ensure = "floating-ip-bulk-{}-ensure".format(address)
    flow = linear_flow.Flow("migrate-floating-ip-{}".format(address))
    flow.add(RetrieveFloatingIP(context.src_cloud,
                                name=floating_ip_binding,
                                provides=floating_ip_binding,
                                rebind=[floating_ip_retrieve]))
    flow.add(EnsureFloatingIPBulk(context.dst_cloud,
                                  name=floating_ip_bulk_ensure,
                                  provides=floating_ip_bulk_ensure,
                                  rebind=[floating_ip_binding]))
    context.store[floating_ip_retrieve] = address
    return flow


def associate_floating_ip_server(context, floating_ip_address,
                                 fixed_ip_info, server_id):
    """Associates Floating IP to Nova instance"""
    floating_ip_bulk_ensure = "floating-ip-bulk-{}-ensure".format(
        floating_ip_address)
    floating_ip_sync = "floating-ip-{}-{}-sync".format(server_id,
                                                       floating_ip_address)
    fixed_ip_address = fixed_ip_info["addr"]
    fixed_ip_nic = "fixed-ip-{}-nic".format(fixed_ip_address)
    server_boot = "server-{}-boot".format(server_id)
    floating_ip_ensure = "floating-ip-{}-ensure".format(floating_ip_address)
    flow = linear_flow.Flow("associate-floating-ip-{}-server-{}"
                            .format(floating_ip_address, server_id))
    flow.add(task_utils.SyncPoint(name=floating_ip_sync,
                                  requires=[floating_ip_bulk_ensure,
                                            server_boot]))
    flow.add(EnsureFloatingIP(context.dst_cloud,
                              name=floating_ip_ensure,
                              provides=floating_ip_ensure,
                              rebind=[server_boot,
                                      floating_ip_bulk_ensure,
                                      fixed_ip_nic]))
    return flow
