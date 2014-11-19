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

from pumphouse import exceptions
from pumphouse import events
from pumphouse import task


LOG = logging.getLogger(__name__)


class RetrieveRole(task.BaseCloudTask):
    def execute(self, role_id):
        role = self.cloud.keystone.roles.get(role_id)
        return role.to_dict()


class EnsureRole(task.BaseCloudTask):
    def execute(self, role_info):
        try:
            role = self.cloud.keystone.roles.find(name=role_info["name"])
        except exceptions.keystone_excs.NotFound:
            role = self.cloud.keystone.roles.create(
                name=role_info["name"],
            )
            LOG.info("Created role: %s", role)
            self.created_event(role)
        return role.to_dict()

    def created_event(self, role):
        events.emit("create", {
            "id": role.id,
            "type": "role",
            "cloud": self.cloud.name,
            "data": role.to_dict(),
        }, namespace="/events")


def migrate_role(context, role_id):
    role_binding = "role-{}".format(role_id)
    role_retrieve = "{}-retrieve".format(role_binding)
    role_ensure = "{}-ensure".format(role_binding)
    flow = linear_flow.Flow("migrate-role-{}".format(role_id)).add(
        RetrieveRole(context.src_cloud,
                     name=role_binding,
                     provides=role_binding,
                     rebind=[role_retrieve]),
        EnsureRole(context.dst_cloud,
                   name=role_ensure,
                   provides=role_ensure,
                   rebind=[role_binding]),
    )
    context.store[role_retrieve] = role_id
    return flow
