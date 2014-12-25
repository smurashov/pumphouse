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

from pumphouse import events
from pumphouse import exceptions
from pumphouse import task


LOG = logging.getLogger(__name__)


class RetrieveTenant(task.BaseCloudTask):
    def execute(self, tenant_id):
        tenant = self.cloud.keystone.tenants.get(tenant_id)
        return tenant.to_dict()


class EnsureTenant(task.BaseCloudTask):
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
            self.created_event(tenant)
        return tenant.to_dict()

    def created_event(self, tenant):
        LOG.info("Tenant created: %s", tenant.id)
        events.emit("create", {
            "id": tenant.id,
            "type": "tenant",
            "cloud": self.cloud.name,
            "data": tenant.to_dict(),
        }, namespace="/events")


class AddTenantAdmin(task.BaseCloudTask):
    def execute(self, tenant_info):
        tenant = self.cloud.keystone.tenants.get(tenant_info["id"])
        user = self.cloud.keystone.auth_ref.user_id
        admin_roles = [r for r in self.cloud.keystone.roles.list()
                       if r.name == "admin"]
        if not admin_roles:
            raise exceptions.NotFound
        admin_role = admin_roles[0]
        try:
            self.cloud.keystone.tenants.add_user(tenant,
                                                 user,
                                                 admin_role)
        except exceptions.keystone_excs.Conflict:
            LOG.warning("User %s is admin in tenant %r", user, tenant)
        return tenant_info


def migrate_tenant(context, tenant_id):
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_retrieve = "{}-retrieve".format(tenant_binding)
    tenant_ensure = "{}-create".format(tenant_binding)
    tenant_addadmin = "{}-ensure".format(tenant_binding)
    flow = linear_flow.Flow("migrate-tenant-{}".format(tenant_id)).add(
        RetrieveTenant(context.src_cloud,
                       name=tenant_binding,
                       provides=tenant_binding,
                       rebind=[tenant_retrieve]),
        EnsureTenant(context.dst_cloud,
                     name=tenant_ensure,
                     provides=tenant_ensure,
                     rebind=[tenant_binding]),
        AddTenantAdmin(context.dst_cloud,
                       name=tenant_addadmin,
                       provides=tenant_addadmin,
                       rebind=[tenant_ensure]),
    )
    context.store[tenant_retrieve] = tenant_id
    return flow
