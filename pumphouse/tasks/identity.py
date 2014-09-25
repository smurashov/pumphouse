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


def migrate_passwords(context, store, users_ids, tenant_id):
    users_ensure = ["user-{}-ensure".format(user_id) for user_id in users_ids]
    passwords_repair = "repair-{}".format(tenant_id)
    task = RepairUsersPasswords(context.src_cloud, context.dst_cloud,
                                name=passwords_repair,
                                requires=users_ensure)
    return (task, store)


def migrate_server_identity(context, store, server_info):
    server_id = server_info["id"]
    flow = graph_flow.Flow("server-identity-{}".format(server_id))
    tenant_id = server_info["tenant_id"]
    user_id = server_info["user_id"]
    tenant_retrieve = "tenant-{}-retrieve".format(tenant_id)
    user_retrieve = "user-{}-retrieve".format(user_id)
    if tenant_retrieve not in store:
        tenant_flow, store = tenant_tasks.migrate_tenant(context, store,
                                                         tenant_id)
        flow.add(tenant_flow)
    if user_retrieve not in store:
        user = context.src_cloud.keystone.users.get(user_id)
        user_tenant_id = getattr(user, "tenantId", None)
        user_flow, store = user_tasks.migrate_user(context, store,
                                                   user_id,
                                                   tenant_id=user_tenant_id)
        flow.add(user_flow)
    roles = context.src_cloud.keystone.users.list_roles(user_id,
                                                        tenant=tenant_id)
    for role in roles:
        role_id = role.id
        role_retrieve = "role-{}-retrieve".format(role_id)
        if role_retrieve not in store:
            role_flow, store = role_tasks.migrate_role(context, store, role_id)
            flow.add(role_flow)

        if role.name.startswith("_"):
            continue
        user_role_ensure = "user-role-{}-{}-{}-ensure".format(user_id,
                                                              role_id,
                                                              tenant_id)
        if user_role_ensure in store:
            continue
        membership_flow, store = user_tasks.migrate_membership(context,
                                                               store,
                                                               user_id,
                                                               role_id,
                                                               tenant_id)
        flow.add(membership_flow)
    return flow, store


def migrate_identity(context, store, tenant_id):
    flow = graph_flow.Flow("identity-{}".format(tenant_id))
    tenant_retrieve = "tenant-{}-retrieve".format(tenant_id)
    if tenant_retrieve not in store:
        tenant_flow, store = tenant_tasks.migrate_tenant(context, store,
                                                         tenant_id)
        flow.add(tenant_flow)
    users_ids, roles_ids = set(), set()
    # XXX(akscram): Due to the bug #1308218 users duplication can be here.
    users = context.src_cloud.keystone.users.list(tenant_id)
    for user in users:
        user_retrieve = "user-{}-retrieve".format(user.id)
        if (user.id == context.src_cloud.keystone.auth_ref.user_id or
                user.id in users_ids or
                user_retrieve in store):
            continue
        user_tenant_id = getattr(user, "tenantId", None)
        user_flow, store = user_tasks.migrate_user(context, store, user.id,
                                                   tenant_id=user_tenant_id)
        flow.add(user_flow)
        users_ids.add(user.id)
        user_roles = context.src_cloud.keystone.users.list_roles(
            user.id, tenant=tenant_id)
        for role in user_roles:
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
            membership_flow, store = user_tasks.migrate_membership(context,
                                                                   store,
                                                                   user.id,
                                                                   role.id,
                                                                   tenant_id)
            flow.add(membership_flow)
    for role_id in roles_ids:
        role_retrieve = "role-{}-retrieve".format(role_id)
        if role_retrieve not in store:
            role_flow, store = role_tasks.migrate_role(context, store, role_id)
            flow.add(role_flow)
    return (users_ids, flow, store)
