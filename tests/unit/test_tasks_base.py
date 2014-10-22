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
    def delete(self):
        self.env.cloud.keystone.tenants.delete(self.tenant["id"])


class Server(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        return (data["tenant_id"], data["id"])

    @Tenant()
    def tenant(self):
        return {"id": self.server["tenant_id"]}

    @base.task(before=[tenant.delete])
    def delete(self):
        self.env.cloud.nova.servers.delete(self.server)


class TenantWorkload(base.Resource):
    tenant = Tenant()

    @base.Collection(Server)
    def servers(self):
        return self.env.cloud.nova.servers.list(search_opts={
            "all_tenants": 1,
            "tenant_id": self.tenant["id"],
        })

    delete = base.task(name="delete",
                       requires=[tenant.delete, servers.each().delete])


class TasksBaseTestCase(unittest.TestCase):
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
