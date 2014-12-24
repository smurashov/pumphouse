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

from pumphouse.tasks.quota import nova, cinder, neutron
from taskflow.patterns import graph_flow


SERVICES = {
    "compute": nova,
    "volume": cinder,
    "network": neutron
}


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
