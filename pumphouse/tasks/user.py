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
from pumphouse import task


LOG = logging.getLogger(__name__)


class RetrieveUser(task.BaseCloudTask):
    def execute(self, user_id):
        user = self.cloud.keystone.users.get(user_id)
        self.cloud.identity.fetch(user.id)
        return user.to_dict()


class EnsureUser(task.BaseCloudTask):
    def execute(self, user_info, tenant_info):
        try:
            user = self.cloud.keystone.users.find(name=user_info["name"])
            # TODO(akscram): Current password should be reseted.
        except exceptions.keystone_excs.NotFound:
            user = self.cloud.keystone.users.create(
                name=user_info["name"],
                # TODO(akscram): Here we should generate a temporary
                #                password for the user and use them
                #                along the migration process.
                #                The RepaireUserPasswords should repaire
                #                original after all operations.
                password="default",
                email=user_info["email"],
                tenant_id=user_info.get("tenantId"),
                enabled=user_info["enabled"],
            )
            LOG.info("Created user: %s", user)
        return user.to_dict()


class EnsureUserRole(task.BaseCloudTask):
    def execute(self, user_info, role_info, tenant_info):
        try:
            self.cloud.keystone.tenants.add_user(tenant_info["id"],
                                                 user_info["id"],
                                                 role_info["id"])
        except exceptions.keystone_excs.Conflict:
            pass
        else:
            LOG.info("Created assinment role %s for user %s in tenant %s",
                     role_info["id"], user_info["id"], tenant_info["id"])
        return user_info


def migrate_membership(src, dst, store, user_id, role_id, tenant_id):
    user_ensure = "user-{}-ensure".format(user_id)
    role_ensure = "role-{}-ensure".format(role_id)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    user_role_ensure = "user-role-{}-{}-{}-ensure".format(user_id, role_id,
                                                          tenant_id)
    task = EnsureUserRole(dst,
                          name=user_role_ensure,
                          provides=user_role_ensure,
                          requires=[user_ensure, role_ensure,
                                    tenant_ensure])
    store[user_role_ensure] = user_role_ensure
    return (task, store)


def migrate_user(src, dst, store, user_id, tenant_id=None):
    user_binding = "user-{}".format(user_id)
    user_retrieve = "{}-retrieve".format(user_binding)
    user_ensure = "{}-ensure".format(user_binding)
    user_ensure_requires = [user_binding]
    if tenant_id is not None:
        tenant_ensure = "tenant-{}-ensure".format(tenant_id)
        user_ensure_requires.append(tenant_ensure)
    flow = linear_flow.Flow("migrate-user-{}".format(user_id)).add(
        RetrieveUser(src,
                     name=user_retrieve,
                     provides=user_binding,
                     requires=[user_retrieve]),
        EnsureUser(dst,
                   name=user_ensure,
                   provides=user_ensure,
                   requires=user_ensure_requires),
    )
    store[user_retrieve] = user_id
    return (flow, store)
