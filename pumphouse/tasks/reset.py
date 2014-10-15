import functools

import taskflow.engines
from taskflow.patterns import graph_flow
import taskflow.task


class AttrDict(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        return "<{}>".format(" ".join("{}={}".format(k, v)
                                      for k, v in self.__dict__.items()))


class UnboundTask(object):
    def __init__(self, fn=None, name=None, requires=[]):
        self._resource_task = {}
        self.fn = fn
        if name is None and fn is not None:
            self.name = fn.__name__
        else:
            self.name = name
        self.requires = requires

    def __call__(self, fn):
        assert self.fn is None and self.name is None
        self.fn = fn
        self.name = fn.__name__
        return self

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if not instance.bound:
            return BoundTask(instance, self)
        else:
            return self.get_for_bound_resource(instance)

    def get_for_bound_resource(self, resource):
        try:
            return self._resource_task[resource]
        except KeyError:
            task = self.realize_with(resource)
            self._resource_task[resource] = task
            return task

    def realize_with(self, resource):
        assert resource.bound
        store = resource.get_store()
        requires = []
        for task in self.requires:
            data = task.resource.get_data(resource)
            bound_res = store.get_resource(task.resource, data)
            requires.append(task.get_for_bound_resource(bound_res))
        return Task(self.fn, self.name, resource, requires=requires)


class BoundTask(object):
    def __init__(self, resource, unbound_task):
        self.resource = resource
        self.task = unbound_task

    def get_for_bound_resource(self, resource):
        return self.task.get_for_bound_resource(resource)

    def __repr__(self):
        return '<{} {} {}>'.format(
            type(self).__name__, self.task.name, self.resource)


class Task(object):
    def __init__(self, fn, name, resource, requires):
        self.fn = fn
        self.name = name
        self.resource = resource
        self.requires = requires

    def get_tasks(self):
        for task in self.requires:
            for _task in task.get_tasks():
                yield _task
        yield self

    def __repr__(self):
        if self.requires:
            requires = ' requires={}'.format(self.requires)
        else:
            requires = ''
        return '<{} {} {}{}>'.format(
            type(self).__name__,
            self.name,
            self.resource,
            requires,
        )

task = UnboundTask


class Resource(object):
    class __metaclass__(type):
        def __new__(mcs, name, bases, cls_vars):
            resources, tasks = [], []
            for k, v in cls_vars.iteritems():
                # Chicken and egg problem
                if name != "Resource" and isinstance(v, Resource):
                    resources.append(k)
                elif isinstance(v, UnboundTask):
                    tasks.append(k)
            cls_vars["_resources"] = tuple(resources)
            cls_vars["_tasks"] = tuple(tasks)
            main_res_name = name.lower()
            if main_res_name.endswith("workload"):
                main_res_name = main_res_name[:-len("workload")]
            cls_vars["_main_resource"] = main_res_name
            return type.__new__(mcs, name, bases, cls_vars)

    def __init__(self, value=None, store=None):
        self._resource_data = {}
        self.store = store
        if value is not None:
            setattr(self, self._main_resource, value)
            self.bound = True
        else:
            self.bound = False

    def get_data(self, resource):
        return self._resource_data[resource]

    def set_data(self, resource, value):
        self._resource_data[resource] = value

    def get_store(self):
        assert self.bound
        if self.store is not None:
            self.store = Store()
        return self.store

    @classmethod
    def get_id_for(cls, data):
        return data.id

    def __get__(self, instance, owner):
        if instance is not None:
            return self.get_data(instance)
        else:
            return self

    def __set__(self, instance, value):
        assert instance is not None
        self.set_data(instance, value)

    def __repr__(self):
        if self.bound:
            value = getattr(self, self._main_resource)
        else:
            value = 'unbound'
        return '<{} {}>'.format(type(self).__name__, value)


class Collection(Resource):
    def __init__(self, base_cls, value=None, store=None):
        super(Collection, self).__init__(value, store)
        self.base_cls = base_cls
        self.list_fn = None

    def list(self, fn):
        self.list_fn = fn
        return self

    def each(self):
        return CollectionProxy(self)

    def get_data(self, resource):
        try:
            return super(Collection, self).get_data(resource)
        except KeyError:
            assert self.list_fn is not None
            data = self.list_fn(resource)
            self.set_data(resource, data)
            return data

    def get_id_for(self, data):
        return frozenset(self.base_cls.get_id_for(el) for el in data)


class CollectionProxy(object):
    def __init__(self, collection):
        self.collection = collection

    def __getattr__(self, name):
        base_cls = self.collection.base_cls
        assert name in base_cls._tasks
        return BoundTask(
            self.collection,
            CollectionUnboundTask(getattr(base_cls, name)),
        )


class CollectionUnboundTask(UnboundTask):
    def __init__(self, task):
        super(CollectionUnboundTask, self).__init__(task.fn, task.requires)
        self.base_task = task

    def realize_with(self, resource):
        assert resource.bound
        requires = []
        for data in resource.collection:
            res = resource.base_cls(data)
            requires.append(self.base_task.get_for_bound_resource(res))
        return Task(
            None,  # Wow! We'll call this None!
            self.name,
            resource,
            requires=requires,
        )


class Server(Resource):
    @task
    def delete(self):
        print "Deleting server", self.server
        #self.cloud.nova.servers.delete(self.server)


class Tenant(Resource):
    @task
    def delete(self):
        print "Deleting tenant", self.tenant
        #self.cloud.keystone.tenants.delete(self.tenant)


class TenantWorkload(Resource):
    tenant = Tenant()
    servers = Collection(Server)

    @servers.list
    def servers(self):
        return [AttrDict(id='servid1', name='server1'),
                AttrDict(id='servid2', name='server2')]
        return self.cloud.nova.servers.list(search_opts={
            "all_tenants": 1,
            "tenant_id": self.tenant.id,
        })

    delete = task(name="delete",
                  requires=[tenant.delete, servers.each().delete])


def delete_tenant(tenant):
    runner = TaskflowRunner()
    workload = runner.store.get_resource(TenantWorkload, tenant)
    runner.add(workload.delete)
    runner.run()


class Store(object):
    def __init__(self):
        self.resources = {}

    def get_resource(self, resource, data):
        if isinstance(resource, Collection):
            base_cls = resource.base_cls
            res_type = functools.partial(Collection, base_cls=base_cls)
            key = (Collection, base_cls, resource.get_id_for(data))
        else:
            if isinstance(resource, type(Resource)):
                res_type = resource
            else:
                res_type = type(resource)
            key = (res_type, res_type.get_id_for(data))
        try:
            return self.resources[key]
        except KeyError:
            res = res_type(value=data, store=self)
            self.resources[key] = res
            return res


class Runner(object):
    def __init__(self):
        self.tasks = []
        self.store = Store()

    def add(self, task):
        self.tasks.extend(task.get_tasks())

    def run(self):
        print("Hey, I'm gonna run these tasks:")
        print("\n".join(map(repr, self.tasks)))


class TaskFlowTask(taskflow.task.Task):
    def __init__(self, task, **kwargs):
        super(TaskFlowTask, self).__init__(**kwargs)
        self.task = task

    def execute(self, **dependencies):
        if self.task.fn is not None:
            self.task.fn(self.task.resource)


class TaskflowRunner(Runner):
    def get_task_prefix(self, task):
        value = getattr(task.resource, task.resource._main_resource)
        return "{}_{}_{}".format(
            type(task.resource).__name__,
            task.resource.get_id_for(value),
            task.name,
        )

    def convert_task(self, task):
        prefix = self.get_task_prefix(task)
        flow_task = TaskFlowTask(
            task,
            name=prefix,
            provides=prefix + "_finished",
            rebind=[self.get_task_prefix(req_task) + "_finished"
                    for req_task in task.requires],
        )
        return flow_task

    def run(self):
        flow = graph_flow.Flow("main flow")
        for task in self.tasks:
            flow.add(self.convert_task(task))
        taskflow.engines.run(flow, engine_conf='parallel')

if __name__ == '__main__':
    try:
        delete_tenant(AttrDict(id='tenid1', name='tenant1'))
    except:
        import traceback
        traceback.print_exc()
        import pdb
        pdb.post_mortem()
