from pumphouse.tasks import base


class AttrDict(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        return "<{}>".format(" ".join("{}={}".format(k, v)
                                      for k, v in self.__dict__.items()))


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
        return [AttrDict(id='servid1', name='server1'),
                AttrDict(id='servid2', name='server2')]
        return self.cloud.nova.servers.list(search_opts={
            "all_tenants": 1,
            "tenant_id": self.tenant.id,
        })

    delete = base.task(name="delete",
                       requires=[tenant.delete, servers.each().delete])


def delete_tenant(tenant):
    runner = base.TaskflowRunner()
    workload = runner.store.get_resource(TenantWorkload, tenant)
    runner.add(workload.delete)
    runner.run()


if __name__ == '__main__':
    try:
        delete_tenant(AttrDict(id='tenid1', name='tenant1'))
    except:
        import traceback
        traceback.print_exc()
        import pdb
        pdb.post_mortem()
