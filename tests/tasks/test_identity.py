import sys
import unittest

from mock import Mock, patch, call
from pumphouse import task

sys.modules["flask.ext"] = Mock()
from pumphouse.tasks import identity
from pumphouse.tasks import role as role_tasks
from pumphouse.tasks import user as user_tasks
from pumphouse.tasks import tenant as tenant_tasks


class TestIdentity(unittest.TestCase):
    def setUp(self):
        self.src_cloud = Mock()
        self.dst_cloud = Mock()
        self.user_id = "dummy_user_id"
        self.tenant_id = "dummy_tenant_id"
        self.server_info = {
            "id": "dummy_server_id",
            "user_id": self.user_id,
            "tenant_id": self.tenant_id
        }
        self.users_ids = ["user1_id", "user2_id"]
        self.user1_info = {
            "id": self.users_ids[0],
            "name": "User1 Name"
        }
        self.user2_info = {
            "id": self.users_ids[1],
            "name": "User2 Name"
        }
        self.users_infos = {
            self.users_ids[0]: self.user1_info,
            self.users_ids[1]: self.user2_info,
        }
        self.src_cloud.identity = self.users_infos
        self.context = Mock(src_cloud=self.src_cloud,
                            dst_cloud=self.dst_cloud,
                            name="Context")


class TestMigratePasswords(TestIdentity):
    @patch.object(identity, "RepairUsersPasswords")
    def test_migrate_passwords(self, mock_repair_user_passwords):
        store = {}
        (task, store) = identity.migrate_passwords(
            self.context,
            store,
            self.users_ids,
            self.tenant_id
        )

        mock_repair_user_passwords.assert_called_once_with(
            self.src_cloud,
            self.dst_cloud,
            requires=["user-%s-ensure" % id for id in self.users_ids],
            name="repair-%s" % self.tenant_id
        )

        self.assertEqual(task, mock_repair_user_passwords())
        self.assertEqual(store, {})


class TestRepairUsersPasswords(TestIdentity):
    def test_execute(self):
        repair_users_passwords = identity.RepairUsersPasswords(self.src_cloud,
                                                               self.dst_cloud)
        repair_users_passwords.execute(**{
            "user-user1_id-ensure": self.user1_info,
            "user-user2_id-ensure": self.user2_info,
        })

        self.assertIsInstance(repair_users_passwords, task.BaseCloudsTask)
        self.assertEqual(
            [i for i in self.dst_cloud.identity.update.call_args[0][0]],
            [
                (self.users_ids[0], self.user1_info),
                (self.users_ids[1], self.user2_info),
            ]
        )
        self.dst_cloud.identity.push.assert_called_once_with()


class TestMigrateIdentityBase(TestIdentity):
    def patchFlows(self, store):
        def patchFlow(cl, method, store):
            mock_flow = patch.object(cl, method).start()
            mock_flow.configure_mock(name=method)
            return_value = Mock(name=method)
            mock_flow.return_value = (return_value, store)
            return mock_flow, return_value

        (self.mock_role, self.mock_role_result) = patchFlow(
            role_tasks,
            "migrate_role",
            store)
        (self.mock_user, self.mock_user_result) = patchFlow(
            user_tasks,
            "migrate_user",
            store)
        (self.mock_member, self.mock_member_result) = patchFlow(
            user_tasks,
            "migrate_membership",
            store)
        (self.mock_tenant, self.mock_tenant_result) = patchFlow(
            tenant_tasks,
            "migrate_tenant",
            store)
        self.addCleanup(patch.stopall)
        return store

    def mockRole(self, id, name):
        r = Mock(id=id, name=name)
        r.name = name
        return r

    def setUp(self):
        super(TestMigrateIdentityBase, self).setUp()

        self.roles = [
            self.mockRole("role1_id", "admin"),
            self.mockRole("role2_id", "_fbi"),
            self.mockRole("role3_id", "user"),
            self.mockRole("role4_id", "superuser"),
        ]
        self.src_cloud.keystone.users.list_roles.return_value = self.roles
        self.src_cloud.keystone.users.get.return_value = Mock(
            tenantId=self.tenant_id
        )

        self.mock_flow_patcher = patch("taskflow.patterns.graph_flow.Flow")
        self.mock_flow = self.mock_flow_patcher.start()


class TestMigrateServerIdentity(TestMigrateIdentityBase):
    def test_migrate_server_identity(self):
        self.store = self.patchFlows(
            {"user-role-%s-%s-%s-ensure" % (self.user_id,
                                            self.roles[3].id,
                                            self.tenant_id): True}
        )

        (flow, store) = identity.migrate_server_identity(
            self.context,
            self.store,
            self.server_info
        )

        self.src_cloud.keystone.users.list_roles.assert_called_once_with(
            self.user_id,
            tenant=self.tenant_id
        )

        self.mock_flow.assert_called_once_with(
            "server-identity-%s" % self.server_info["id"]
        )

        # Tenant migration task created
        self.assertEqual(
            self.mock_tenant.call_args_list,
            [call(self.context, self.store, self.tenant_id), ]
        )

        # User migration task created
        self.assertEqual(
            self.mock_user.call_args_list,
            [
                call(self.context,
                     self.store,
                     self.user_id,
                     tenant_id=self.tenant_id)
            ]
        )

        # Tasks for each of roles
        self.assertEqual(
            self.mock_role.call_args_list,
            [call(self.context, self.store, r.id) for r in self.roles]
        )

        # Tasks for memberships of 0 and 2
        # [1] is skipped since it is started from "_"
        # [3] is skipped since there is such task in store already
        self.assertEqual(
            self.mock_member.call_args_list,
            [
                call(self.context,
                     self.store,
                     self.user_id,
                     r.id,
                     self.tenant_id)
                for r in [self.roles[0], self.roles[2]]
            ]
        )

    def test_migrate_server_identity_tenant_and_user_exist(self):
        self.store = self.patchFlows({
            "tenant-%s-retrieve" % self.tenant_id: True,
            "user-%s-retrieve" % self.user_id: True,
        })

        (flow, store) = identity.migrate_server_identity(
            self.context,
            self.store,
            self.server_info
        )

        # Assert neither migrate_tenant nor migrate_user are called if
        # corresponding ones exist in store
        self.assertFalse(self.mock_tenant.called)
        self.assertFalse(self.mock_user.called)

    def test_migrate_server_return(self):
        self.src_cloud.keystone.users.list_roles.return_value = [self.roles[0]]

        (flow, store) = identity.migrate_server_identity(
            self.context,
            {},
            self.server_info
        )

        self.assertEqual(store, {
            "role-role1_id-retrieve": "role1_id",
            "tenant-dummy_tenant_id-retrieve": "dummy_tenant_id",
            "user-dummy_user_id-retrieve": "dummy_user_id",
            "user-role-dummy_user_id-role1_id-dummy_tenant_id-ensure":
                "user-role-dummy_user_id-role1_id-dummy_tenant_id-ensure"
        })
        self.assertEqual(flow, self.mock_flow.return_value)


class TestMigrateIdentity(TestMigrateIdentityBase):
    def mockUser(self, id, name):
        u = Mock(id=id, name=name, tenantId=self.tenant_id)
        u.name = name
        return u

    def setUp(self):
        super(TestMigrateIdentity, self).setUp()

        self.users = [
            self.mockUser(u["id"], u["name"])
            for u in [self.user1_info, self.user2_info]
        ]
        # Emulate users duplication in keystone.users.list
        self.users.append(self.users[0])

        self.src_cloud.keystone.users.list.return_value = self.users

    def test_migrate_identity(self):
        self.store = self.patchFlows({
            "user-role-%s-%s-%s-ensure" % (self.user1_info["id"],
                                           self.roles[3].id,
                                           self.tenant_id): True,
            "user-role-%s-%s-%s-ensure" % (self.user2_info["id"],
                                           self.roles[3].id,
                                           self.tenant_id): True,
        })

        (users_ids,
         flow,
         store) = identity.migrate_identity(self.context,
                                            self.store,
                                            self.tenant_id)

        self.mock_flow.assert_called_once_with("identity-%s" % self.tenant_id)

        # Tenant migration task created
        self.assertEqual(
            self.mock_tenant.call_args_list,
            [call(self.context, self.store, self.tenant_id), ]
        )

        # Tasks for all unique users created
        self.assertEqual(
            self.mock_user.call_args_list,
            [
                call(self.context, self.store, self.user1_info["id"],
                     tenant_id=self.tenant_id),
                call(self.context, self.store, self.user2_info["id"],
                     tenant_id=self.tenant_id),
            ]
        )

        # For both unique users only roles [0] and [2] should be migrated as
        # [1] starts with "_" and
        # [4] exists for both of them in store
        self.assertEqual(
            self.mock_member.call_args_list,
            [
                call(self.context, self.store, u["id"], r.id, self.tenant_id)
                for u in [self.user1_info, self.user2_info]
                for r in [self.roles[0], self.roles[2]]
            ]
        )

        self.assertItemsEqual(
            self.mock_role.call_args_list,
            [
                call(self.context, self.store, r.id)
                for r in [self.roles[0], self.roles[2], self.roles[3]]
            ]
        )

    def test_migrate_identity_return(self):
        self.src_cloud.keystone.users.list_roles.return_value = [self.roles[0]]
        self.store = {}
        (users_ids, flow, store) = identity.migrate_identity(self.context,
                                                             self.store,
                                                             self.tenant_id)

        self.assertEqual(store, {
            "role-role1_id-retrieve": "role1_id",
            "tenant-dummy_tenant_id-retrieve": "dummy_tenant_id",
            "user-role-user1_id-role1_id-dummy_tenant_id-ensure":
                "user-role-user1_id-role1_id-dummy_tenant_id-ensure",
            "user-role-user2_id-role1_id-dummy_tenant_id-ensure":
                "user-role-user2_id-role1_id-dummy_tenant_id-ensure",
            "user-user1_id-retrieve": "user1_id",
            "user-user2_id-retrieve": "user2_id"
        })
        self.assertEqual(flow, self.mock_flow.return_value)
        self.assertItemsEqual(users_ids, [self.users_ids[0],
                              self.users_ids[1]])


if __name__ == "__main__":
    unittest.main()
