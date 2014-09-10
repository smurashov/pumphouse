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

from pumphouse import task
from pumphouse.tasks import role as role_tasks
from pumphouse.tasks import tenant as tenant_tasks
from pumphouse.tasks import user as user_tasks


LOG = logging.getLogger(__name__)


class RepairUsersPasswords(task.BaseCloudsTask):
    def execute(self, **users_infos):
        def with_mapping(identity):
            for user_id in mapping:
                yield user_id, self.src_cloud.identity[user_id]

        mapping = dict((source.split("-", 2)[1], user_info["id"])
                       for source, user_info in users_infos.iteritems())
        self.dst_cloud.identity.update(with_mapping(self.src_cloud.identity))
        self.dst_cloud.identity.push()


def migrate_passwords(src, dst, store, users_ids, tenant_id):
    users_ensure = ["user-{}-ensure".format(user_id) for user_id in users_ids]
    passwords_repair = "repair-{}".format(tenant_id)
    task = RepairUsersPasswords(src, dst,
                                name=passwords_repair,
                                requires=users_ensure)
    return (task, store)


def migrate_identity(src, dst, store, tenant_id):
    flow = graph_flow.Flow("identity-{}".format(tenant_id))
    tenant_retrieve = "tenant-{}-retrieve".format(tenant_id)
    if tenant_retrieve not in store:
        tenant_flow, store = tenant_tasks.migrate_tenant(src, dst, store,
                                                         tenant_id)
        flow.add(tenant_flow)
    users_ids, roles_ids = set(), set()
    # XXX(akscram): Due to the bug #1308218 users duplication can be here.
    for user in src.keystone.users.list(tenant_id):
        user_retrieve = "user-{}-retrieve".format(user.id)
        if (user.id in (users_ids, src.keystone.auth_ref.user_id) or
                user_retrieve in store):
            continue
        user_tenant_id = getattr(user, "tenantId", None)
        user_flow, store = user_tasks.migrate_user(src, dst, store, user.id,
                                                   tenant_id=user_tenant_id)
        flow.add(user_flow)
        users_ids.add(user.id)
        for role in src.keystone.users.list_roles(user.id, tenant=tenant_id):
            # NOTE(akscram): Actually all roles which started with
            #                underscore are hidden.
            if role.name.startswith("_"):
                continue
            roles_ids.add(role.id)
            user_role_ensure = "user-role-{}-{}-{}-ensure".format(user.id,
                                                                  role.id,
                                                                  tenant_id)
            if user_role_ensure in store:
                continue
            membership_flow, store = user_tasks.migrate_membership(src, dst,
                                                                   store,
                                                                   user.id,
                                                                   role.id,
                                                                   tenant_id)
            flow.add(membership_flow)
    for role_id in roles_ids:
        role_retrieve = "role-{}-retrieve".format(role_id)
        if role_retrieve not in store:
            role_flow, store = role_tasks.migrate_role(src, dst, store,
                                                       role_id)
            flow.add(role_flow)
    # TODO(akcram): All users' passwords should be restored when all
    #               migration operations ended.
    users_passwords_flow, store = migrate_passwords(src, dst,
                                                    store,
                                                    users_ids,
                                                    tenant_id)
    flow.add(users_passwords_flow)
    return (flow, store)