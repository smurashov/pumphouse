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
                self.created_event(address)
        else:
            LOG.warn("Already exists, %s", floating_ip.to_dict())
        return floating_ip.to_dict()

    def created_event(self, address):
        events.emit("floating_ip created", {
            "id": address,
            "cloud": self.cloud.name
        }, namespace="/events")

    def not_added_event(self, address):
        events.emit("floating_ip error", {
            "id": address,
            "cloud": self.cloud.name
        }, namespace="/events")


class EnsureFloatingIP(task.BaseCloudTask):
    # TODO(ogelbukh): this task must be refactored in a way that replaces a
    # while loop with built-in retry mechanism of Taskflow lib
    def execute(self, server_info, floating_ip_address, fixed_ip_info):
        fixed_ip_address = fixed_ip_info["addr"]
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
        events.emit("floating_ip assigned", {
            "id": address,
            "server_id": server_id,
            "cloud": self.cloud.name
        }, namespace="/events")

    def assigning_error_event(self, address, server_id):
        events.emit("floating_ip assign error", {
            "id": address,
            "server_id": server_id,
            "cloud": self.cloud.name
        }, namespace="/events")


def migrate_floating_ip(context, store, address):
    """Replicate Floating IP from source cloud to destination cloud"""
    floating_ip_binding = "floating-ip-{}".format(address)
    floating_ip_retrieve = "floating-ip-{}-retrieve".format(address)
    floating_ip_bulk_ensure = "floating-ip-bulk-{}-ensure".format(address)
    flow = linear_flow.Flow("migrate-floating-ip-{}".format(address))
    flow.add(RetrieveFloatingIP(context.src_cloud,
                                name=floating_ip_retrieve,
                                provides=floating_ip_retrieve,
                                rebind=[floating_ip_binding]))
    flow.add(EnsureFloatingIPBulk(context.dst_cloud,
                                  name=floating_ip_bulk_ensure,
                                  provides=floating_ip_bulk_ensure,
                                  rebind=[floating_ip_retrieve]))
    store[floating_ip_binding] = address
    return flow, store


def associate_floating_ip_server(context, store, floating_ip_address,
                                 fixed_ip_info, server_id):
    """Associates Floating IP to Nova instance"""
    floating_ip_binding = "floating-ip-{}".format(floating_ip_address)
    floating_ip_sync = "floating-ip-{}-{}-sync".format(server_id,
                                                       floating_ip_address)
    fixed_ip_binding = "fixed-ip-{}".format(server_id)
    server_boot = "server-{}-boot".format(server_id)
    floating_ip_ensure = "flotaing-ip-{}-ensure".format(floating_ip_address)
    flow = linear_flow.Flow("associate-floating-ip-{}-server-{}"
                            .format(floating_ip_address, server_id))
    flow.add(task_utils.SyncPoint(name=floating_ip_sync,
                                  requires=[floating_ip_binding,
                                            server_boot]))
    flow.add(EnsureFloatingIP(context.dst_cloud,
                              name=floating_ip_binding,
                              provides=floating_ip_ensure,
                              rebind=[server_boot,
                                      floating_ip_binding,
                                      fixed_ip_binding]))
    store[fixed_ip_binding] = fixed_ip_info
    return flow, store
