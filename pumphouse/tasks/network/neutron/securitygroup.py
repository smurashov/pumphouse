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
from taskflow.patterns import graph_flow
from . import utils

LOG = logging.getLogger(__name__)


def get_securityGroups_by(neutron, security_groups_filter):
    try:
        return neutron.list_security_groups(
            **security_groups_filter)['security_groups']

    except Exception as e:
        raise e


def create_securityGroup_rule(neutron, security_group_rule_info):
    try:
        return neutron.create_security_group_rule(
            {'security_group_rule': security_group_rule_info})
    except Exception as e:
        raise e


def create_security_group(neutron, security_group_info):
    try:
        return neutron.create_security_group(
            {'security_group': security_group_info})['security_group']
    except Exception as e:
        raise e


class RetrieveSecurityGroups(task.BaseCloudTask):

    def execute(self):
        return get_securityGroups_by(self.cloud.neutron, {})


class RetrieveSecurityGroupById(task.BaseCloudTask):

    def execute(self, all_security_groups, security_id):
        for security_group in all_security_groups:
            if (security_group['id'] == security_id):
                return security_group

        return None


class EnsureSecurityGroup(task.BaseCloudTask):

    def execute(self, all_security_groups, security_group_info, port_info):

        for security_group in all_security_groups:
            if (security_group['name'] == security_group_info['name']):
                # XXX check security group assigned to port
                LOG.info("security '%s' group already exists %s" %
                         (security_group['name'], str(security_group)))
                return security_group

        LOG.info("security '%s' group not exists" %
                 security_group_info['name'])

        security_group_rules = security_group_info['security_group_rules']

        del security_group_info['id'], security_group_info[
            'security_group_rules']
        security_group = create_security_group(
            self.cloud.neutron, security_group_info)

        for rule in security_group_rules:
            del rule['id'], rule['tenant_id']
            rule['security_group_id'] = security_group['id']
            create_securityGroup_rule(self.cloud.neutron, rule)

        if security_group['id'] not in port_info['security_groups']:
            port_info['security_groups'].append(security_group['id'])
            self.cloud.neutron.update_port(port_info['id'], {
                'port': {'security_groups': port_info['security_groups']}
            })

        return security_group


def migrate_securityGroup(context, securityGroup_id, port_binding):
    securityGroup_binding = securityGroup_id

    securityGroup_retrieve = "\
        securityGroup-{}-retrieve".format(securityGroup_binding)
    securityGroup_ensure = "\
        securityGroup-{}-ensure".format(
        securityGroup_binding)

    if (securityGroup_binding in context.store):
        return None, securityGroup_ensure

    context.store[securityGroup_binding] = securityGroup_id

    f = graph_flow.Flow(
        "neutron-securityGroup-migration-{}".format(securityGroup_id))

    all_dst, all_src, all_src_retrieve, all_dst_retrieve = \
        utils.generate_retrieve_binding("NeutronAllSecurityGroups")

    if (all_src not in context.store):

        f.add(RetrieveSecurityGroups(
            context.src_cloud,
            name=all_src,
            provides=all_src_retrieve
        ))

        context.store[all_src] = None

    if (all_dst not in context.store):

        f.add(RetrieveSecurityGroups(
            context.dst_cloud,
            name=all_dst,
            provides=all_dst_retrieve
        ))

        context.store[all_dst] = None

    f.add(RetrieveSecurityGroupById(context.src_cloud,
                                    name=securityGroup_retrieve,
                                    provides=securityGroup_retrieve,
                                    rebind=[
                                        all_src_retrieve,
                                        securityGroup_binding
                                    ]))

    f.add(EnsureSecurityGroup(context.dst_cloud,
                              name=securityGroup_ensure,
                              provides=securityGroup_ensure,
                              rebind=[
                                  all_dst_retrieve,
                                  securityGroup_retrieve,
                                  port_binding
                              ]))

    return f, securityGroup_ensure
