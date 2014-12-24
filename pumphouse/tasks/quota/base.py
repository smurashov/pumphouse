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


LOG = logging.getLogger(__name__)


class RetrieveTenantQuota(task.BaseCloudTask):
    client = None

    def execute(self, tenant_id):
        quota = self.client.quotas.get(tenant_id)
        return quota._info


class RetrieveDefaultQuota(task.BaseCloudTask):
    client = None

    def execute(self, tenant_id):
        quota = self.client.quotas.defaults(tenant_id)
        return quota._info


class EnsureTenantQuota(task.BaseCloudTask):
    client = None

    def execute(self, quota_info, tenant_info):
        tenant_id = tenant_info["id"]
        quota = self.client.quotas.update(tenant_id,
                                          **quota_info)
        LOG.info("Quota updated: %r", quota)
        return quota._info


class EnsureDefaultQuota(task.BaseCloudTask):
    client = None

    def execute(self, quota_info):
        quota = self.client.quota_classes.update("default",
                                                 **quota_info)
        LOG.info("Quota updated: %r", quota)
        return quota._info
