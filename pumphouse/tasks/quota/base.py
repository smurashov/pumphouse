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

from pumphouse.quota import nova, cinder, neutron


LOG = logging.getLogger(__name__)
SERVICES = {
    "nova": nova,
    "cinder": cinder,
    "neutron": neutron
}


class RetrieveTenantQuota(task.BaseCloudTask):
    client = None

    def execute(self, tenant_id):
        quota = self.client.quotas.get(tenant_id)
        return quota.to_dict()


class RetrieveDefaultQuota(task.BaseCloudTask):
    client = None

    def execute(self, tenant_id):
        quota = self.client.quotas.defaults(tenant_id)
        return quota.to_dict()


class EnsureTenantQuota(task.BaseCloudTask):
    client = None

    def execute(self, quota_info, tenant_info):
        tenant_id = tenant_info["id"]
        quota = self.client.quotas.update(tenant_id,
                                          **quota_info)
        LOG.info("Quota updated: %r", quota)
        return quota.to_dict()


class EnsureDefaultQuota(task.BaseCloudTask):
    client = None

    def execute(self, quota_info):
        quota = self.client.quota_classes.update("default",
                                                 **quota_info)
        LOG.info("Quota updated: %r", quota)
        return quota.to_dict()


def migrate_tenant_quota(context, service_name, tenant_id):
    service = SERVICES[service_name]
    flow = graph_flow.Flow("migrate-{}-quota-{}".format(service_name,
                                                        tenant_id))
    quota_binding = "quota-{}-{}".format(service_name,
                                         tenant_id)
    quota_ensure = "{}-ensure".format(quota_binding)
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_ensure = "{}-ensure".format(tenant_binding)
    flow.add(
        service.RetrieveTenantQuota(context.src_cloud,
                                    name=quota_binding,
                                    provides=quota_binding,
                                    rebind=[tenant_binding]),
        service.EnsureTenantQuota(context.dst_cloud,
                                  name=quota_ensure,
                                  provides=quota_ensure,
                                  rebind=[quota_binding,
                                          tenant_ensure]),
    )
    return flow


def migrate_default_quota(context, service_name):
    service = SERVICES[service_name]
    flow = graph_flow.Flow("migrate-{}-quota-default".format(service_name))
    quota_binding = "quota-{}-default".format(service_name)
    quota_ensure = "{}-ensure".format(quota_binding)
    flow.add(
        service.RetrieveDefaultQuota(context.src_cloud,
                                     name=quota_binding,
                                     provides=quota_binding),
        service.EnsureTenantQuota(context.dst_cloud,
                                  name=quota_ensure,
                                  provides=quota_ensure,
                                  rebind=[quota_binding]),
    )
    return flow
