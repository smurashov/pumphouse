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
        events.emit("tenant create", {
            "id": tenant.id,
            "name": tenant.name,
            "cloud": self.cloud.name,
        }, namespace="/events")


def migrate_tenant(src, dst, store, tenant_id):
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_retrieve = "{}-retrieve".format(tenant_binding)
    tenant_ensure = "{}-ensure".format(tenant_binding)
    flow = linear_flow.Flow("migrate-tenant-{}".format(tenant_id)).add(
        RetrieveTenant(src,
                       name=tenant_retrieve,
                       provides=tenant_binding,
                       rebind=[tenant_retrieve]),
        EnsureTenant(dst,
                     name=tenant_ensure,
                     provides=tenant_ensure,
                     rebind=[tenant_binding]),
    )
    store[tenant_retrieve] = tenant_id
    return (flow, store)
