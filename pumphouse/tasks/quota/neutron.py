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

from pumphouse import task


LOG = logging.getLogger(__name__)


class RetrieveTenantQuota(task.BaseCloudTask):
    def execute(self, tenant_id):
        quota = self.cloud.neutron.show_quota(tenant_id)
        return quota


class RetrieveDefaultQuota(task.BaseCloudTask):
    pass


class EnsureTenantQuota(task.BaseCloudTask):
    def execute(self, quota_info, tenant_info):
        tenant_id = tenant_info["id"]
        quota = self.cloud.neutron.update_quota(tenant_id,
                                                quota_info)
        LOG.info("Quota updated: %r", quota)
        return quota


class EnsureDefaultQuota(task.BaseCloudTask):
    pass
