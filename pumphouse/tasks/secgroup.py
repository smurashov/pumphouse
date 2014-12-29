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

from pumphouse import task
from pumphouse import events
from pumphouse import exceptions


LOG = logging.getLogger(__name__)


class RetrieveSecGroup(task.BaseCloudTask):
    """Retrieve security group data from cloud by ID"""
    def execute(self, secgroup_id, tenant_info, user_info):
        secgroup = self.cloud.nova.security_groups.get(secgroup_id)
        return secgroup.to_dict()


class EnsureSecGroup(task.BaseCloudTask):
    """Create security group with given parameters in cloud"""
    def execute(self, secgroup_info, tenant_info, user_info):
        cloud = self.cloud.restrict(tenant_name=tenant_info["name"],
                                    username=user_info["name"],
                                    password="default")
        try:
            secgroup = cloud.nova.security_groups.find(
                name=secgroup_info["name"])
        except exceptions.nova_excs.NotFound:
            secgroup = cloud.nova.security_groups.create(
                secgroup_info["name"], secgroup_info["description"])
            LOG.info("Created: %s", secgroup.to_dict())
            self.created_event(secgroup.to_dict())
        else:
            LOG.warn("Already exists: %s", secgroup.to_dict())
        secgroup = self._add_rules(secgroup.id, secgroup_info)
        return secgroup.to_dict()

    def created_event(self, secgroup_info):
        events.emit("create", {
            "id": secgroup_info["id"],
            "type": "secgroup",
            "cloud": self.cloud.name,
            "data": secgroup_info,
        }, namespace="/events")

    def _add_rules(self, secgroup_id, secgroup_info):
        """This helper function recreates all rules from security group"""
        rules_list = secgroup_info["rules"]
        for rule in rules_list:
            try:
                rule = self.cloud.nova.security_group_rules.create(
                    secgroup_id,
                    ip_protocol=rule["ip_protocol"],
                    from_port=rule["from_port"],
                    to_port=rule["to_port"],
                    cidr=rule["ip_range"]["cidr"])
            except exceptions.nova_excs.BadRequest:
                LOG.warn("Duplicate rule: %s", rule)
                pass
            except KeyError:
                LOG.warn("Broken rule: %s", rule)
                pass
            except exceptions.nova_excs.NotFound:
                LOG.exception("No such security group exist: %s",
                              secgroup_info)
                raise
            else:
                LOG.info("Created: %s", rule)
        secgroup = self.cloud.nova.security_groups.get(secgroup_id)
        return secgroup


def migrate_secgroup(context, secgroup_id, tenant_id, user_id):
    secgroup_binding = "secgroup-{}".format(secgroup_id)
    secgroup_retrieve = "{}-retrieve".format(secgroup_binding)
    secgroup_ensure = "{}-ensure".format(secgroup_binding)
    tenant_binding = "tenant-{}".format(tenant_id)
    tenant_ensure = "{}-ensure".format(tenant_binding)
    user_binding = "user-{}".format(user_id)
    user_ensure = "{}-ensure".format(user_binding)
    flow = linear_flow.Flow("migrate-secgroup-{}".format(secgroup_id))
    flow.add(RetrieveSecGroup(context.src_cloud,
                              name=secgroup_binding,
                              provides=secgroup_binding,
                              rebind=[secgroup_retrieve,
                                      tenant_binding,
                                      user_binding]))
    flow.add(EnsureSecGroup(context.dst_cloud,
                            name=secgroup_ensure,
                            provides=secgroup_ensure,
                            rebind=[secgroup_binding,
                                    tenant_ensure,
                                    user_ensure]))
    context.store[secgroup_retrieve] = secgroup_id
    return flow
