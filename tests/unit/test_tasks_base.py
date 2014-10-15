import unittest

import mock

from pumphouse.tasks import base


class Server(base.Resource):
    @base.task
    def delete(self):
        print "Deleting server", self.server
        #self.cloud.nova.servers.delete(self.server)


class Tenant(base.Resource):
    @base.task
    def delete(self):
        print "Deleting tenant", self.tenant
        #self.cloud.keystone.tenants.delete(self.tenant)


class TenantWorkload(base.Resource):
    tenant = Tenant()
    servers = base.Collection(Server)

    @servers.list
    def servers(self):
        return [mock.Mock(id='servid1', name='server1'),
                mock.Mock(id='servid2', name='server2')]
        return self.cloud.nova.servers.list(search_opts={
            "all_tenants": 1,
            "tenant_id": self.tenant.id,
        })

    delete = base.task(name="delete",
                       requires=[tenant.delete, servers.each().delete])


class TasksBaseTestCase(unittest.TestCase):
    def test_basic_tasks(self):
        tenant = mock.Mock(id='tenid1', name='tenant1')
        runner = base.TaskflowRunner()
        workload = runner.store.get_resource(TenantWorkload, tenant)
        runner.add(workload.delete)
        runner.run()
