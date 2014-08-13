import logging

from taskflow import task

from pumphouse import exceptions


LOG = logging.getLogger(__name__)


class BaseCloudTask(task.Task):
    def __init__(self, cloud, *args, **kwargs):
        super(BaseCloudTask, self).__init__(*args, **kwargs)
        self.cloud = cloud


class BaseCloudsTask(task.Task):
    def __init__(self, src_cloud, dst_cloud, *args, **kwargs):
        super(BaseCloudsTask, self).__init__(*args, **kwargs)
        self.src_cloud = src_cloud
        self.dst_cloud = dst_cloud


class BaseRetrieveTask(BaseCloudTask):
    def execute(self, obj_id):
        obj = self.retrieve(obj_id)
        serialized_obj = self.serialize(obj)
        return serialized_obj

    def retrieve(self, obj_id):
        raise NotImplementedError()

    def serialize(self, obj):
        return obj.to_dict()


class RetrieveTenant(BaseRetrieveTask):
    def retrieve(self, tenant_id):
        tenant = self.cloud.keystone.tenants.get(tenant_id)
        return tenant


class EnsureTenant(BaseCloudTask):
    def execute(self, tenant_info):
        try:
            tenant = self.cloud.keystone.tenants.find(name=tenant_info["name"])
        except exceptions.keystone_excs.NotFound:
            tenant = self.cloud.keystone.tenants.create(
                tenant_info["name"],
                description=tenant_info["description"],
                enabled=tenant_info["enabled"],
            )
            LOG.info("Created tenant: %s", tenant)
        return tenant.to_dict()


class EnsureAdminInTenant(BaseCloudTask):
    def execute(self, user_id, tenant_id):
        pass


class RetrieveUser(BaseRetrieveTask):
    def retrieve(self, user_id):
        user = self.cloud.keystone.users.get(user_id)
        self.cloud.identity.fetch(user.id)
        return user


class EnsureUser(BaseCloudTask):
    def execute(self, user_info, tenant_info):
        try:
            user = self.cloud.keystone.users.find(name=user_info["name"])
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
                # TODO(akscram): Members of the tenant can be from
                #                another tenant.
                tenant_id=tenant_info["id"],
                enabled=user_info["enabled"],
            )
            LOG.info("Created user: %s", user)
        return user.to_dict()


class RepaireUserPasswords(BaseCloudsTask):
    def execute(self, **users_infos):
        def with_mapping(identity):
            for user_id, password in identity.iteritems():
                yield mapping[user_id], password

        mapping = dict((source.split("-", 2)[1], user_info["id"])
                       for source, user_info in users_infos.iteritems())
        self.dst_cloud.identity.update(with_mapping(self.src_cloud.identity))
        self.dst_cloud.identity.push()


class EnsureUserRole(BaseCloudTask):
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


class RetrieveRole(BaseRetrieveTask):
    def retrieve(self, role_id):
        role = self.cloud.keystone.roles.get(role_id)
        return role


class EnsureRole(BaseCloudTask):
    def execute(self, role_info):
        try:
            role = self.cloud.keystone.roles.find(name=role_info["name"])
        except exceptions.keystone_excs.NotFound:
            role = self.cloud.keystone.roles.create(
                name=role_info["name"],
            )
            LOG.info("Created role: %s", role)
        return role.to_dict()
