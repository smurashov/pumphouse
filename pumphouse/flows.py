import taskflow.engines
from taskflow.patterns import graph_flow, linear_flow

from pumphouse import tasks


def migrate_tenant(src, dst, tenant_id):
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_retrieve = "{}-retrieve".format(tenant_binding)
    tenant_ensure = "{}-ensure".format(tenant_binding)
    flow = linear_flow.Flow("migrate-tenant-{}".format(tenant_id)).add(
        tasks.RetrieveTenant(src,
                             name=tenant_retrieve,
                             provides=tenant_binding,
                             rebind=[tenant_retrieve],
                             inject={tenant_retrieve: tenant_id}),
        tasks.EnsureTenant(dst,
                           name=tenant_ensure,
                           provides=tenant_ensure,
                           rebind=[tenant_binding]),
    )
    return flow


def migrate_user(src, dst, user_id, tenant_id):
    user_binding = "user-{}".format(user_id)
    user_retrieve = "{}-retrieve".format(user_binding)
    user_ensure = "{}-ensure".format(user_binding)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    flow = linear_flow.Flow("migrate-user-{}".format(user_id)).add(
        tasks.RetrieveUser(src,
                           name=user_retrieve,
                           provides=user_binding,
                           rebind=[user_retrieve],
                           inject={user_retrieve: user_id}),
        tasks.EnsureUser(dst,
                         name=user_ensure,
                         provides=user_ensure,
                         rebind=[user_binding, tenant_ensure]),
    )
    return flow


def migrate_role(src, dst, role_id):
    role_binding = "role-{}".format(role_id)
    role_retrieve = "{}-retrieve".format(role_binding)
    role_ensure = "{}-ensure".format(role_binding)
    flow = linear_flow.Flow("migrate-role-{}".format(role_id)).add(
        tasks.RetrieveRole(src,
                           name=role_retrieve,
                           provides=role_binding,
                           rebind=[role_retrieve],
                           inject={role_retrieve: role_id}),
        tasks.EnsureRole(dst,
                         name=role_ensure,
                         provides=role_ensure,
                         rebind=[role_binding]),
    )
    return flow


def migrate_flavor(src, dst, flavor_id):
    flavor_binding = "flavor-{}".format(flavor_id)
    flavor_retrieve = "{}-retrieve".format(flavor_binding)
    flavor_ensure = "{}-ensure".format(flavor_binding)
    flow = linear_flow.Flow("migrate-flavor-{}".format(flavor_id)).add(
        tasks.RetrieveFlavor(src,
                             name=flavor_retrieve,
                             provides=flavor_binding,
                             rebind=[flavor_retrieve],
                             inject={flavor_retrieve: flavor_id}),
        tasks.EnsureFlavor(dst,
                           name=flavor_ensure,
                           provides=flavor_ensure,
                           rebind=[flavor_binding]),
    )
    return flow


def migrate_membership(src, dst, user_id, role_id, tenant_id):
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
    return task


def migrate_passwords(src, dst, users_ids):
    users_ensure = ["user-{}-ensure".format(user_id) for user_id in users_ids]
    task = tasks.RepaireUsersPasswords(src, dst,
                                       requires=users_ensure)
    return task


def migrate_identity(src, dst, tenant_id):
    flow = graph_flow.Flow("identity-{}".format(tenant_id))
    tenant_flow = migrate_tenant(src, dst, tenant_id)
    flow.add(tenant_flow)
    users_ids, roles_ids = set(), set()
    # XXX(akscram): Due to the bug #1308218 users duplication can be here.
    for user in src.keystone.users.list(tenant_id):
        if user.id in users_ids:
            continue
        user_flow = migrate_user(src, dst, user.id, tenant_id)
        flow.add(user_flow)
        users_ids.add(user.id)
        for role in src.keystone.users.list_roles(user.id, tenant=tenant_id):
            # NOTE(akscram): Actually all roles which started with
            #                underscore are hidden.
            if role.name.startswith("_"):
                continue
            membership_flow = migrate_membership(src, dst, user.id, role.id,
                                                 tenant_id)
            flow.add(membership_flow)
            roles_ids.add(role.id)
    for role_id in roles_ids:
        role_flow = migrate_role(src, dst, role_id)
        flow.add(role_flow)
    # TODO(akcram): All users' passwords should be restored when all
    #               migration operations ended.
    users_passwords_flow = migrate_passwords(src, dst, users_ids)
    flow.add(users_passwords_flow)
    return flow


def run_flow(flow, store):
    result = taskflow.engines.run(flow, engine_conf='parallel', store=store)
    return result
