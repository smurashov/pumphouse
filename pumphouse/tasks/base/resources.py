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

from . import tasks

__all__ = ['Resource', 'Collection']


class SelfDataAttr(object):
    def __init__(self):
        self._instance_data = {}

    def __get__(self, instance, owner):
        assert instance is not None
        return self._instance_data[instance]

    def __set__(self, instance, value):
        self._instance_data[instance] = value


class Resource(object):
    class __metaclass__(type):
        def __new__(mcs, name, bases, cls_vars):
            resources, tasks_ = [], []
            for k, v in cls_vars.items():
                # Chicken and egg problem
                if name != "Resource" and isinstance(v, Resource):
                    resources.append(k)
                elif isinstance(v, tasks.UnboundTask):
                    tasks_.append(k)
            cls_vars["_resources"] = tuple(resources)
            cls_vars["_tasks"] = tuple(tasks_)
            main_res_name = name.lower()
            if main_res_name.endswith("workload"):
                main_res_name = main_res_name[:-len("workload")]
            cls_vars["_main_resource"] = main_res_name
            if name != "Collection" and main_res_name not in resources:
                cls_vars[main_res_name] = SelfDataAttr()
            return type.__new__(mcs, name, bases, cls_vars)

    def __init__(self, data=None, runner=None):
        self._resource_subres = {}
        self.runner = runner
        self.bound = False
        self.data_fn = None
        if data is not None:
            self.bound = True
            setattr(self, self._main_resource, data)

    def set_data_fn(self, data_fn):
        self.data_fn = data_fn
        return self

    __call__ = set_data_fn

    def get_bound_subres(self, resource, data=None):
        assert not self.bound
        assert resource.bound
        try:
            return self._resource_subres[resource]
        except KeyError:
            assert data is not None or self.data_fn is not None
        if data is None:
            data = self.data_fn(resource)
        res = resource.get_runner().get_resource(self, data)
        self._resource_subres[resource] = res
        return res

    def get_data(self):
        assert self.bound
        return getattr(self, self._main_resource)

    def set_data(self, data):
        assert self.bound
        setattr(self, self._main_resource, data)

    def get_runner(self):
        assert self.bound
        assert self.runner is not None
        return self.runner

    @classmethod
    def get_id_for(cls, data):
        try:
            return data["id"]
        except KeyError:
            return data["name"]

    def __get__(self, instance, owner):
        if instance is not None:
            bound_res = self.get_bound_subres(instance)
            return bound_res.get_data()
        else:
            return self

    def __set__(self, instance, value):
        bound_res = self.get_bound_subres(instance, data=value)
        bound_res.set_data(value)

    def __repr__(self):
        if self.bound:
            value = getattr(self, self._main_resource)
        else:
            value = 'unbound'
        return '<{} {}>'.format(type(self).__name__, value)

    @property
    def env(self):
        return self.runner.env


class Collection(Resource):
    def __init__(self, base_cls, **kwargs):
        super(Collection, self).__init__(**kwargs)
        self.base_cls = base_cls

    def each(self):
        return CollectionProxy(self)

    def get_id_for(self, data):
        elements = frozenset(self.base_cls.get_id_for(el) for el in data)
        return (self.base_cls, elements)


class CollectionProxy(object):
    def __init__(self, collection):
        self.collection = collection

    def __getattr__(self, name):
        base_cls = self.collection.base_cls
        assert name in base_cls._tasks
        return tasks.BoundTask(
            self.collection,
            CollectionUnboundTask(getattr(base_cls, name)),
        )


class CollectionUnboundTask(tasks.UnboundTask):
    def __init__(self, task):
        super(CollectionUnboundTask, self).__init__(
            task.fn,
            requires=task.requires,
        )
        self.base_task = task

    def realize_with(self, resource):
        assert resource.bound
        runner = resource.get_runner()
        requires = []
        for data in resource.collection:
            res = runner.get_resource(resource.base_cls, data)
            requires.append(self.base_task.get_for_bound_resource(res))
        return tasks.Task(
            None,  # Wow! We'll call this None!
            self.name,
            resource,
            requires=requires,
        )
