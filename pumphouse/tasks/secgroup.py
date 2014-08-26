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


from pumphouse import exceptions
from pumphouse import task


LOG = logging.getLogger(__name__)


class RetrieveSecGroup(task.BaseCloudTask):
    def execute(self, secgroup_id):
        secgroup = self.cloud.nova.security_groups.get(secgroup_id)
        return secgroup.to_dict()


class RetrieveSecGroupRules(task.BaseCloudTask):
    def execute(self, secgroup_id):
        secgroup = self.cloud.nova.security_groups.get(secgroup_id)
        return secgroup.rules


class EnsureSecGroup(task.BaseCloudTask):
    def execute(self, secgroup_info):
        try: 
            secgroup = self.cloud.nova.security_groups.find(
                name=secgroup_info["name"])
        except exceptions.nova_excs.NotFound:
            secgroup = self.cloud.nova.security_groups.create(
                secgroup_info["name"], secgroup_info["description"])
            LOG.info("Created: %s", secgroup.to_dict())
        else:
            LOG.warn("Already exists: %s", secgroup.to_dict())
        return secgroup.to_dict()


class EnsureSecGroupRules(task.BaseCloudTask):
    def execute(self, secgroup_info):
        rules_list = secgroup_info["rules"]
        for rule in rules_list:
            try:
                rule = self.cloud.nova.security_group_rules.create(
                    secgroup_info["id"],
                    ip_protocol=rule["ip_protocol"],
                    from_port=rule["from_port"],
                    to_port=rule["to_port"],
                    cidr=rule["ip_range"]["cidr"])
            except exceptions.nova_excs.BadRequest:
                LOG.warn("Duplicate rule: %s", rule)
            except exceptions.nova_excs.NotFound:
                LOG.exception("No such security group exist: %s",
                              secgroup_info)
            else:
                LOG.info("Created: %s", rule)
                return rule.to_dict()

def migrate_secgroup(src, dst, store, secgroup_id):
    pass
