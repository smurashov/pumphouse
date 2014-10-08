class UnboundTask(object):
    def __init__(self, fn, requires=[]):
        self.fn = fn
        self.name = fn.__name__
        self.requires = requires

    def __get__(self, instance, owner):
        if instance is not None:
            return BoundTask(instance, self)
        else:
            return self


class BoundTask(object):
    def __init__(self, resource, unbound_task):
        self.resource = resource
        self.task = unbound_task

    def realize(self):
        assert self.resource.bound
        requires = []
        for task in self.task.requires:
            data = task.resource.get_data(self.resource)
            bound_res = task.resource.bind(data)
            requires.append(task.rebind(bound_res).realize())
        return Task(
            self.task.fn,
            self.task.name,
            self.resource,
            requires=requires,
        )

    def rebind(self, resource):
        return type(self)(resource, self.task)

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


def task(fn=None, **kwargs):
    def _get_task(fn):
        return UnboundTask(fn, **kwargs)

    if fn is None:
        return _get_task
    else:
        return _get_task(fn)


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

    def __init__(self, value=None):
        self._resource_data = {}
        if value is not None:
            setattr(self, self._main_resource, value)
            self.bound = True
        else:
            self.bound = False

    def get_data(self, resource):
        return self._resource_data[resource]

    def set_data(self, resource, value):
        self._resource_data[resource] = value

    def bind(self, value):
        return type(self)(value)

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
    def __init__(self, base_cls, value=None):
        # This is the most magic class here
        super(Collection, self).__init__(value)
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

    def bind(self, value):
        return type(self)(self.base_cls, value)


class CollectionProxy(object):
    def __init__(self, collection):
        self.collection = collection

    def __getattr__(self, name):
        base_cls = self.collection.base_cls
        assert name in base_cls._tasks
        return CollectionTask(self.collection, getattr(base_cls, name))


class CollectionTask(BoundTask):
    def realize(self):
        assert self.resource.bound
        requires = []
        for data in self.resource.collection:
            res = self.resource.base_cls(data)
            requires.append(BoundTask(res, self.task).realize())
        return Task(
            None,  # Wow! We'll call this None!
            self.task.name,
            self.resource,
            requires=requires,
        )


class Workload(Resource):
    pass


class Server(Resource):
    @task
    def delete(self):
        self.cloud.nova.servers.delete(self.server)


class Tenant(Resource):
    @task
    def delete(self):
        self.cloud.keystone.tenants.delete(self.tenant)


class TenantWorkload(Workload):
    tenant = Tenant()
    servers = Collection(Server)

    @servers.list
    def servers(self):
        return ['server1', 'server2']
        return self.cloud.nova.servers.list(search_opts={
            "all_tenants": 1,
            "tenant_id": self.tenant.id,
        })

    @task(requires=[tenant.delete, servers.each().delete])
    def delete(self):
        pass


def delete_tenant(tenant):
    runner = TaskflowRunner()
    runner.add(TenantWorkload(tenant).delete)
    runner.run()


class Runner(object):
    def __init__(self):
        self.tasks = []

    def add(self, task):
        real_task = task.realize()
        self.tasks.extend(real_task.get_tasks())

    def run(self):
        print "Hey, I'm gonna run these tasks:", self.tasks


class TaskflowRunner(Runner):
    pass


if __name__ == '__main__':
    delete_tenant(123)
