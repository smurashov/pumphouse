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

import mock

from pumphouse.tasks import base


class Tenant(base.Resource):
    @base.task
    def create(self):
        self.data = self.env.cloud.keystone.tenants.create(self.data)

    @base.task
    def delete(self):
        self.env.cloud.keystone.tenants.delete(self.data["id"])


class Server(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        try:
            tenant_id = data["tenant_id"]
        except KeyError:
            tenant_id = Tenant.get_id_for(data["tenant"])
        return (tenant_id, super(Server, cls).get_id_for(data))

    @Tenant()
    def tenant(self):
        if "tenant_id" in self.data:
            return {"id": self.data["tenant_id"]}
        elif "tenant" in self.data:
            return self.data["tenant"]
        else:
            assert False

    @base.task(requires=[tenant.create])
    def create(self):
        server = self.data.copy()
        server.pop("tenant")
        server["tenant_id"] = self.tenant["id"]
        self.data = self.env.cloud.nova.servers.create(server)

    @base.task(before=[tenant.delete])
    def delete(self):
        self.env.cloud.nova.servers.delete(self.data)


class TenantWorkload(base.Resource):
    @Tenant()
    def tenant(self):
        return self.data

    @base.Collection(Server)
    def servers(self):
        return self.env.cloud.nova.servers.list(search_opts={
            "all_tenants": 1,
            "tenant_id": self.tenant["id"],
        })

    delete = base.task(name="delete",
                       requires=[tenant.delete, servers.each().delete])
    create = base.task(name="create",
                       requires=[tenant.create, servers.each().create])


class TasksBaseTestCase(unittest.TestCase):
    def test_create_tasks(self):
        tenant = {"name": "tenant1"}
        created_tenant = dict(tenant, id="tenid1")
        servers = [
            {"name": "server1", "tenant": tenant},
            {"name": "server2", "tenant": tenant},
        ]
        env = mock.Mock()
        env.cloud.keystone.tenants.create.return_value = created_tenant

        runner = base.TaskflowRunner(env)
        workload = runner.get_resource(TenantWorkload, tenant)
        workload.servers = servers
        runner.add(workload.create)
        runner.run()

        self.assertEqual(
            env.cloud.keystone.tenants.create.call_args_list,
            [mock.call(tenant)],
        )
        self.assertItemsEqual(
            env.cloud.nova.servers.create.call_args_list,
            map(mock.call, [
                {"tenant_id": created_tenant["id"], "name": server["name"]}
                for server in servers
            ]),
        )
        self.assertEqual(len(env.method_calls), 1 + len(servers))

    def test_delete_tasks(self):
        tenant = {"id": "tenid1", "name": "tenant1"}
        servers = [
            {"id": "servid1", "name": "server1", "tenant_id": tenant["id"]},
            {"id": "servid2", "name": "server2", "tenant_id": tenant["id"]},
        ]
        env = mock.Mock()
        env.cloud.nova.servers.list.return_value = servers
        env.cloud.keystone.tenants.get.return_value = tenant

        runner = base.TaskflowRunner(env)
        workload = runner.get_resource(TenantWorkload, tenant)
        runner.add(workload.delete)
        runner.run()

        self.assertEqual(
            env.cloud.nova.servers.list.call_args_list,
            [mock.call(search_opts={
                "all_tenants": 1,
                "tenant_id": tenant["id"],
            })],
        )
        self.assertEqual(
            env.cloud.keystone.tenants.delete.call_args_list,
            [mock.call(tenant["id"])],
        )
        self.assertItemsEqual(
            env.cloud.nova.servers.delete.call_args_list,
            map(mock.call, servers),
        )
        self.assertEqual(len(env.method_calls), 2 + len(servers))
