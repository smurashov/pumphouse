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

from pumphouse import exceptions
from pumphouse import events
from pumphouse import task


LOG = logging.getLogger(__name__)


class RetrieveKeyPair(task.BaseCloudTask):
    def execute(self, key_name, tenant_info, user_info):
        cloud = self.cloud.restrict(username=user_info["name"],
                                    password="default",
                                    tenant_name=tenant_info["name"])
        keypair = cloud.nova.keypairs.get(key_name)
        # NOTE(akscram): The keypair.user_id is a actual owner of the key pair.
        keypair_info = keypair.to_dict()
        return keypair_info


class DeleteKeyPair(task.BaseCloudTask):
    def execute(self, keypair_info, tenant_info, user_info):
        cloud = self.cloud.restrict(username=user_info["name"],
                                    password="default",
                                    tenant_name=tenant_info["name"])
        cloud.nova.keypairs.delete(keypair_info["name"])
        self.delete_event(keypair_info)
        return keypair_info

    def delete_event(self, keypair_info):
        LOG.info("Deleted keypair: %s", keypair_info["name"])
        events.emit("delete", {
            "id": keypair_info["name"],
            "type": "keypair",
            "cloud": self.cloud.name,
            "data": None,
        }, namespace="/events")


class EnsureKeyPair(task.BaseCloudTask):
    def execute(self, keypair_info, tenant_info, user_info):
        cloud = self.cloud.restrict(username=user_info["name"],
                                    password="default",
                                    tenant_name=tenant_info["name"])
        try:
            keypair = cloud.nova.keypairs.get(keypair_info["name"])
        except exceptions.nova_excs.NotFound:
            keypair = cloud.nova.keypairs.create(
                name=keypair_info["name"],
                public_key=keypair_info["public_key"])
            self.create_event(keypair)
        else:
            if keypair.fingerprint != keypair_info["fingerprint"]:
                msg = ("There is keypair with the same name {!r} but with the"
                       " different fingerprint.".format(keypair_info["name"]))
                raise exceptions.Conflict(msg)
        return keypair.to_dict()

    def create_event(self, keypair):
        LOG.info("Created keypair: %s", keypair.name)
        events.emit("create", {
            "id": keypair.name,
            "type": "keypair",
            "cloud": self.cloud.name,
            "data": keypair.to_dict(),
        }, namespace="/events")


def migrate_keypair(context, flow, tenant_id, user_id, key_name):
    keypair_retrieve = "keypair-{}-retrieve".format(key_name)

    if keypair_retrieve in context.store:
        return None

    user_binding = "user-{}".format(user_id)
    user_ensure = "user-{}-ensure".format(user_id)
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)

    keypair_binding = "keypair-{}".format(key_name)
    keypair_ensure = "keypair-{}-ensure".format(key_name)

    if flow is None:
        flow = graph_flow.Flow(name=user_binding)

    flow.add(
        RetrieveKeyPair(context.src_cloud,
                        name=keypair_binding,
                        provides=keypair_binding,
                        rebind=[
                            keypair_retrieve,
                            tenant_binding,
                            user_binding,
                        ]),
        EnsureKeyPair(context.dst_cloud,
                      name=keypair_ensure,
                      provides=keypair_ensure,
                      rebind=[
                          keypair_binding,
                          tenant_ensure,
                          user_ensure,
                      ]),
    )
    context.store[keypair_retrieve] = key_name
    return flow
