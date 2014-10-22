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


class IdAttr(object):
    def __init__(self, resource):
        self.resource = resource

    def __get__(self, instance, owner):
        return self.resource.get_id(instance)

    def __set__(self, instance, value):
        self.resource.set_id(instance, value)


class Resource(object):
    class __metaclass__(type):
        def __new__(mcs, name, bases, cls_vars):
            resources, tasks_ = [], []
            for k, v in cls_vars.items():
                # Chicken and egg problem
                if name != "Resource" and isinstance(v, Resource):
                    resources.append(k)
                    cls_vars[k + "_id"] = IdAttr(v)
                elif isinstance(v, tasks.UnboundTask):
                    tasks_.append(k)
            cls_vars["_resources"] = tuple(resources)
            cls_vars["_tasks"] = tuple(tasks_)
            main_res_name = name.lower()
            if main_res_name.endswith("workload"):
                main_res_name = main_res_name[:-len("workload")]
            cls_vars["_main_resource"] = main_res_name
            res = type.__new__(mcs, name, bases, cls_vars)
            if name != "Collection" and main_res_name not in resources:
                self_attr = res()
                setattr(res, main_res_name, self_attr)
                setattr(res, main_res_name + "_id", IdAttr(self_attr))
            return res

    def __init__(self, id_=None, value=None, runner=None):
        self._resource_id = {}
        self._resource_data = {}
        self.runner = runner
        self.bound = False
        if id_ is not None:
            setattr(self, self._main_resource + "_id", id_)
            self.bound = True
        if value is not None:
            setattr(self, self._main_resource, value)
            self.bound = True
        self.id_fn = None
        self.data_fn = None

    def by_id(self, id_fn):
        self.id_fn = id_fn
        return self

    def by_data(self, data_fn):
        self.data_fn = data_fn
        return self

    __call__ = by_id

    def get_id(self, resource):
        try:
            return self._resource_id[resource]
        except KeyError:
            if self.id_fn is None:
                raise
            id_ = self.id_fn(resource)
            self.set_id(resource, id_)
            return id_

    def set_id(self, resource, id_):
        self._resource_id[resource] = id_

    def get_data(self, resource):
        try:
            return self._resource_data[resource]
        except KeyError:
            if self.data_fn is not None:
                data = self.data_fn(resource)
            else:
                id_ = self.get_id(resource)
                data = self.from_id(id_)
            self.set_data(resource, data)
            return data

    def set_data(self, resource, value):
        self._resource_data[resource] = value

    def get_runner(self):
        assert self.bound
        assert self.runner is not None
        return self.runner

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
            try:
                value = getattr(self, self._main_resource)
            except (AttributeError, KeyError):
                value = getattr(self, self._main_resource + "_id")
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

    __call__ = Resource.by_data

    def each(self):
        return CollectionProxy(self)

    def get_id_for(self, data):
        return frozenset(self.base_cls.get_id_for(el) for el in data)


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
