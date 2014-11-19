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

import unittest
from mock import Mock, patch, call

from pumphouse import task
from pumphouse import events
from pumphouse import exceptions
from pumphouse.tasks import secgroup


class SecGroupTestCase(unittest.TestCase):
    def setUp(self):
        self.test_secgroup_id = "123"
        self.test_rule_id = "203"
        self.test_secgroup_name = "test-secgroup-name"
        self.test_secgroup_rules = [{
            "ip_protocol": "test_proto",
            "from_port": "80",
            "to_port": "80",
            "ip_range": {
                "cidr": "0.0.0.0/0"
            }}]
        self.secgroup_info = {
            "id": self.test_secgroup_id,
            "name": self.test_secgroup_name,
            "description": "test-secgroup-desc",
            "rules": self.test_secgroup_rules
        }

        self.test_tenant_id = "234"
        self.tenant_info = {
            "id": self.test_tenant_id,
            "name": "test-tenant-name"
        }

        self.test_user_id = "345"
        self.user_info = {
            "id": self.test_user_id,
            "name": "test-user-name"
        }

        self.secgroup = Mock()
        self.secgroup.id = self.test_secgroup_id
        self.secgroup.to_dict.return_value = self.secgroup_info

        self.cloud = Mock()
        self.cloud.restrict.return_value = self.cloud
        self.cloud.nova.security_groups.get.return_value = self.secgroup
        self.cloud.nova.security_groups.create.return_value = self.secgroup
        self.cloud.nova.security_groups.find.return_value = self.secgroup
        self.cloud.nova.security_group_rules.create.return_value = \
            self.test_rule_id

        self.src = Mock()

        self.dst = Mock()

        self.context = Mock()
        self.context.src_cloud = self.src
        self.context.dst_cloud = self.dst
        self.context.store = {}


class TestRetrieveSecGroup(SecGroupTestCase):
    def test_retrieve_is_task(self):
        retrieve_secgroup = secgroup.RetrieveSecGroup(self.cloud)
        self.assertIsInstance(retrieve_secgroup, task.BaseCloudTask)

    def test_retrieve(self):
        retrieve_secgroup = secgroup.RetrieveSecGroup(self.cloud)
        secgroup_info = retrieve_secgroup.execute(self.test_secgroup_id,
                                                  self.tenant_info,
                                                  self.user_info)
        self.cloud.nova.security_groups.get.assert_called_once_with(
            self.test_secgroup_id)
        self.assertEqual("123", secgroup_info["id"])
        self.assertEqual(self.test_secgroup_rules, secgroup_info["rules"])


class TestEnsureSecGroup(SecGroupTestCase):
    def test_ensure_is_task(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        self.assertIsInstance(ensure_secgroup, task.BaseCloudTask)

    def test_execute(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        ensure_secgroup._add_rules = Mock()
        ensure_secgroup._add_rules.return_value = self.secgroup

        # Test that nova.security_groups.create method is not callled unless
        # method nova.security_groups.find with the name of the security group
        # in the source cloud raises NotFound in the dest cloud
        secgroup_info = ensure_secgroup.execute(self.secgroup_info,
                                                self.tenant_info,
                                                self.user_info)
        # Verify that cloud.restrict method is called with correct username and
        # tenant name parameters and with default password for replicated user
        self.cloud.restrict.assert_called_once_with(
            tenant_name=self.tenant_info["name"],
            username=self.user_info["name"],
            password="default")
        self.cloud.nova.security_groups.find.assert_called_once_with(
            name=self.secgroup_info["name"])
        ensure_secgroup._add_rules.assert_called_once_with(
            self.test_secgroup_id, self.secgroup_info)
        self.assertFalse(self.cloud.nova.security_groups.create.called)
        self.assertEqual(self.secgroup_info, secgroup_info)

    def test_execute_not_found(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        ensure_secgroup._add_rules = Mock()
        ensure_secgroup._add_rules.return_value = self.secgroup
        ensure_secgroup.created_event = Mock()
        ensure_secgroup.created_event.return_value = None

        # Test that nova.security_groups.create method is called properly if
        # method nova.security_groups.find raises NotFound exception
        self.cloud.nova.security_groups.find.side_effect = \
            exceptions.nova_excs.NotFound("404 Not Found")
        secgroup_info = ensure_secgroup.execute(self.secgroup_info,
                                                self.tenant_info,
                                                self.user_info)

        self.cloud.nova.security_groups.create.assert_called_once_with(
            self.secgroup_info["name"], self.secgroup_info["description"])
        ensure_secgroup.created_event.assert_called_once_with(
            self.secgroup_info)
        self.assertEqual(secgroup_info, self.secgroup_info)

    def test_created_event(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        events.emit = Mock()
        event_dict = {
            "id": self.test_secgroup_id,
            "type": "secgroup",
            "cloud": self.cloud.name,
            "data": self.secgroup_info,
        }
        ensure_secgroup.created_event(self.secgroup_info)
        events.emit.assert_called_once_with("create",
                                            event_dict,
                                            namespace="/events")

    def test_add_rules(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        secgroup_obj = ensure_secgroup._add_rules(self.test_secgroup_id,
                                                  self.secgroup_info)
        self.assertEqual(self.secgroup, secgroup_obj)
        self.assertEqual(self.cloud.nova.security_group_rules.create.called,
                         len(self.test_secgroup_rules))
        self.cloud.nova.security_groups.get.assert_called_once_with(
            self.test_secgroup_id)

    def test_add_rules_not_found(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        self.cloud.nova.security_group_rules.create.side_effect = \
            exceptions.nova_excs.NotFound("404 Not Found")
        with self.assertRaises(exceptions.nova_excs.NotFound):
            ensure_secgroup._add_rules(self.test_secgroup_id,
                                       self.secgroup_info)

    def test_add_rules_bad_request(self):
        ensure_secgroup = secgroup.EnsureSecGroup(self.cloud)
        self.cloud.nova.security_group_rules.create.side_effect = \
            exceptions.nova_excs.BadRequest("401 Bad Request")
        secgroup_obj = ensure_secgroup._add_rules(self.test_secgroup_id,
                                                  self.secgroup_info)
        self.assertEqual(self.secgroup, secgroup_obj)


class TestMigrateSecGroup(SecGroupTestCase):

    @patch.object(secgroup, "EnsureSecGroup")
    @patch.object(secgroup, "RetrieveSecGroup")
    @patch("taskflow.patterns.linear_flow.Flow")
    def test_migrate_secgroup(self,
                              flow_mock,
                              retrieve_secgroup_mock,
                              ensure_secgroup_mock):
        secgroup_binding = "secgroup-{}".format(self.test_secgroup_id)
        secgroup_retrieve = "{}-retrieve".format(secgroup_binding)

        flow = secgroup.migrate_secgroup(
            self.context,
            self.test_secgroup_id,
            self.test_tenant_id,
            self.test_user_id)

        self.assertEqual({secgroup_retrieve: self.test_secgroup_id},
                         self.context.store)
        flow_mock.assert_called_once_with("migrate-secgroup-{}"
                                          .format(self.test_secgroup_id))
        self.assertEqual(flow.add.call_args_list,
                         [call(retrieve_secgroup_mock()),
                          call(ensure_secgroup_mock())])


if __name__ == '__main__':
    unittest.main()
