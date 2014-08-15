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

from taskflow import task

from pumphouse import exceptions
from pumphouse import utils


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
                # TODO(akscram): Members of the tenant can be from
                #                another tenant.
                tenant_id=tenant_info["id"],
                enabled=user_info["enabled"],
            )
            LOG.info("Created user: %s", user)
        return user.to_dict()


class RepaireUsersPasswords(BaseCloudsTask):
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


class RetrieveFlavor(BaseCloudTask):
    def execute(self, flavor_id):
        flavor = self.cloud.nova.flavors.get(flavor_id)
        return flavor.to_dict()


class EnsureFlavor(BaseCloudTask):
    def execute(self, flavor_info):
        try:
            # TODO(akscram): Ensure that the flavor with the same ID is
            #                equal to the source flavor.
            flavor = self.cloud.nova.flavors.get(flavor_info["id"])
        except exceptions.nova_excs.NotFound:
            flavor = self.cloud.nova.flavors.create(
                flavor_info["name"],
                flavor_info["ram"],
                flavor_info["vcpus"],
                flavor_info["disk"],
                flavorid=flavor_info["id"],
                ephemeral=flavor_info["ephemeral"],
                swap=flavor_info["swap"] or 0,
                rxtx_factor=flavor_info["rxtx_factor"],
                is_public=flavor_info["is_public"],
            )
        return flavor.to_dict()


class EnsureImage(BaseCloudsTask):
    def execute(self, image_id, kernel_info, ramdisk_info):
        image_info = self.src_cloud.glance.images.get(image_id)
        images = self.dst_cloud.glances.images.list(filters={
            # FIXME(akscram): Not all images have the checksum property.
            "checksum": image_info["checksum"],
            "name": image_info["name"],
        })
        try:
            # XXX(akscram): More then one images can be here. Now we
            #               just ignore this fact.
            image = next(iter(images))
        except StopIteration:
            image = self.dst_cloud.glances.images.create(
                disk_format=image_info["disk_format"],
                container_format=image_info["container_format"],
                visibility=image_info["visibility"],
                min_ram=image_info["min_ram"],
                min_disk=image_info["min_disk"],
                name=image_info["name"],
                protected=image_info["protected"],
                kernel_id=kernel_info["id"] if kernel_info else None,
                ramdisk_id=ramdisk_info["id"] if ramdisk_info else None,
            )
            # TODO(akscram): Chunked request is preferred. So in the
            #                future we can control this for generating
            #                the progress of the upload.
            data = self.src_cloud.glance.images.data(image_info["id"])
            self.dst_cloud.glance.images.upload(image["id"], data._resp)
        return dict(image)


class RetrieveServer(BaseCloudTask):
    def execute(self, server_id):
        server = self.cloud.nova.servers.get(server_id)
        return server.to_dict()


class SuspendServer(BaseCloudTask):
    def execute(self, server_info):
        self.cloud.nova.servers.suspend(server_info)
        server = utils.wait_for(server_info, self.cloud.nova.servers.get,
                                value="SUSPENDED")
        return server.to_dict()

    def revert(self, server_info, result, flow_failures):
        self.cloud.nova.servers.resume(server_info)
        server = utils.wait_for(server_info, self.cloud.nova.servers.get,
                                value="ACTIVE")
        return server.to_dict()


class BootServerFromImage(BaseCloudTask):
    def execute(self, server_info, image_info, flavor_info):
        # TODO(akscram): Network information doesn't saved.
        server = self.cloud.nova.servers.create(server_info["name"],
                                                image_info["id"],
                                                flavor_info["id"])
        server = utils.wait_for(server, self.cloud.nova.servers.get,
                                value="ACTIVE")
        return server.to_dict()


class TerminateServer(BaseCloudTask):
    def execute(self, server_info):
        self.cloud.nova.servers.delete(server_info)
