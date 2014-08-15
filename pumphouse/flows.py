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

import taskflow.engines
from taskflow.patterns import graph_flow, linear_flow

from pumphouse import tasks


def migrate_tenant(src, dst, store, tenant_id):
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_retrieve = "{}-retrieve".format(tenant_binding)
    tenant_ensure = "{}-ensure".format(tenant_binding)
    flow = linear_flow.Flow("migrate-tenant-{}".format(tenant_id)).add(
        tasks.RetrieveTenant(src,
                             name=tenant_retrieve,
                             provides=tenant_binding,
                             rebind=[tenant_retrieve]),
        tasks.EnsureTenant(dst,
                           name=tenant_ensure,
                           provides=tenant_ensure,
                           rebind=[tenant_binding]),
    )
    store[tenant_retrieve] = tenant_id
    return (flow, store)


def migrate_user(src, dst, store, user_id, tenant_id):
    user_binding = "user-{}".format(user_id)
    user_retrieve = "{}-retrieve".format(user_binding)
    user_ensure = "{}-ensure".format(user_binding)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    flow = linear_flow.Flow("migrate-user-{}".format(user_id)).add(
        tasks.RetrieveUser(src,
                           name=user_retrieve,
                           provides=user_binding,
                           rebind=[user_retrieve]),
        tasks.EnsureUser(dst,
                         name=user_ensure,
                         provides=user_ensure,
                         rebind=[user_binding, tenant_ensure]),
    )
    store[user_retrieve] = user_id
    return (flow, store)


def migrate_role(src, dst, store, role_id):
    role_binding = "role-{}".format(role_id)
    role_retrieve = "{}-retrieve".format(role_binding)
    role_ensure = "{}-ensure".format(role_binding)
    flow = linear_flow.Flow("migrate-role-{}".format(role_id)).add(
        tasks.RetrieveRole(src,
                           name=role_retrieve,
                           provides=role_binding,
                           rebind=[role_retrieve]),
        tasks.EnsureRole(dst,
                         name=role_ensure,
                         provides=role_ensure,
                         rebind=[role_binding]),
    )
    store[role_retrieve] = role_id
    return (flow, store)


def migrate_flavor(src, dst, store, flavor_id):
    flavor_binding = "flavor-{}".format(flavor_id)
    flavor_retrieve = "{}-retrieve".format(flavor_binding)
    flavor_ensure = "{}-ensure".format(flavor_binding)
    flow = linear_flow.Flow("migrate-flavor-{}".format(flavor_id)).add(
        tasks.RetrieveFlavor(src,
                             name=flavor_retrieve,
                             provides=flavor_binding,
                             requires=[flavor_retrieve]),
        tasks.EnsureFlavor(dst,
                           name=flavor_ensure,
                           provides=flavor_ensure,
                           requires=[flavor_binding]),
    )
    store[flavor_retrieve] = flavor_id
    return flow


def migrate_image(src, dst, store, image_id):
    image_retrieve = "image-{}-retrieve".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)
    requires, inject = [image_retrieve], {}
    image = src.glance.images.get(image_id)
    flow = graph_flow.Flow("migrate-image-{}".format(image_id))
    if hasattr(image, "kernel_id"):
        kernel_retrieve = "image-{}-retrieve".format(image["kernel_id"])
        kernel_ensure = "image-{}-ensure".format(image["kernel_id"])
        flow.add(tasks.EnsureImage(src, dst,
                                   name=kernel_ensure,
                                   provides=kernel_ensure,
                                   requires=(kernel_retrieve,),
                                   inject={"kernel_id": None,
                                           "ramdisk_id": None}))
        store[kernel_retrieve] = image["kernel_id"]
        requires.append(kernel_ensure)
    else:
        inject["kernel_id"] = None
    if hasattr(image, "ramdisk_id"):
        ramdisk_retrieve = "image-{}-retrieve".format(image["ramdisk_id"])
        ramdisk_ensure = "image-{}-ensure".format(image["ramdisk_id"])
        flow.add(tasks.EnsureImage(src, dst,
                                   name=ramdisk_ensure,
                                   provides=ramdisk_ensure,
                                   requires=(ramdisk_retrieve,),
                                   inject={"kernel_id": None,
                                           "ramdisk_id": None}))
        store[ramdisk_retrieve] = image["ramdisk_id"]
        requires.append(ramdisk_ensure)
    else:
        inject["ramdisk_id"] = None
    flow.add(tasks.EnsureImage(src, dst,
                               name=image_ensure,
                               provides=image_ensure,
                               inject=inject,
                               requires=requires))
    store[image_retrieve] = image_id
    return (flow, store)


def migrate_membership(src, dst, store, user_id, role_id, tenant_id):
    user_ensure = "user-{}-ensure".format(user_id)
    role_ensure = "role-{}-ensure".format(role_id)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    user_role_ensure = "user-role-{}-{}-{}-ensure".format(user_id, role_id,
                                                          tenant_id)
    task = tasks.EnsureUserRole(dst,
                                name=user_role_ensure,
                                provides=user_role_ensure,
                                rebind=[user_ensure, role_ensure,
                                        tenant_ensure])
    return (task, store)


def migrate_passwords(src, dst, store, users_ids):
    users_ensure = ["user-{}-ensure".format(user_id) for user_id in users_ids]
    task = tasks.RepaireUsersPasswords(src, dst,
                                       requires=users_ensure)
    return (task, store)


def migrate_identity(src, dst, store, tenant_id):
    flow = graph_flow.Flow("identity-{}".format(tenant_id))
    tenant_flow, store = migrate_tenant(src, dst, store, tenant_id)
    flow.add(tenant_flow)
    users_ids, roles_ids = set(), set()
    # XXX(akscram): Due to the bug #1308218 users duplication can be here.
    for user in src.keystone.users.list(tenant_id):
        if user.id in users_ids:
            continue
        user_flow, store = migrate_user(src, dst, store, user.id, tenant_id)
        flow.add(user_flow)
        users_ids.add(user.id)
        for role in src.keystone.users.list_roles(user.id, tenant=tenant_id):
            # NOTE(akscram): Actually all roles which started with
            #                underscore are hidden.
            if role.name.startswith("_"):
                continue
            membership_flow, store = migrate_membership(src, dst, store,
                                                        user.id, role.id,
                                                        tenant_id)
            flow.add(membership_flow)
            roles_ids.add(role.id)
    for role_id in roles_ids:
        role_flow, store = migrate_role(src, dst, store, role_id)
        flow.add(role_flow)
    # TODO(akcram): All users' passwords should be restored when all
    #               migration operations ended.
    users_passwords_flow = migrate_passwords(src, dst, users_ids)
    flow.add(users_passwords_flow)
    return (flow, store)


def migrate_server(src, dst, store, server_id, image_id, flavor_id):
    server_binding = "server-{}".format(server_id)
    server_retrieve = "server-{}-retrieve".format(server_id)
    server_suspend = "server-{}-suspend".format(server_id)
    server_boot = "server-{}-boot".format(server_id)
    image_ensure = "image-{}-ensure".format(image_id)
    flavor_ensure = "flavor-{}-ensure".format(flavor_id)
    flow = linear_flow.Flow("migrate-server-{}".format(server_id))
    flow.add(tasks.RetrieveServer(src,
                                  name=server_binding,
                                  provides=server_retrieve,
                                  requires=[server_binding]))
    flow.add(tasks.SuspendServer(src,
                                 name=server_binding,
                                 provides=server_suspend,
                                 requires=[server_retrieve]))
    flow.add(tasks.BootServerFromImage(dst,
                                       name=server_binding,
                                       provides=server_boot,
                                       requires=[server_suspend, image_ensure,
                                                 flavor_ensure]
                                       ))
    flow.add(tasks.TerminateServer(src,
                                   name=server_binding,
                                   requires=[server_suspend]))
    store[server_binding] = server_id
    return (flow, store)


def run_flow(flow, store):
    result = taskflow.engines.run(flow, engine_conf='parallel', store=store)
    return result
