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


class Resource(object):
    class __metaclass__(type):
        def __new__(mcs, name, bases, cls_vars):
            resources, tasks_ = [], []
            for k, v in cls_vars.iteritems():
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
            return type.__new__(mcs, name, bases, cls_vars)

    def __init__(self, value=None, runner=None):
        self._resource_data = {}
        self.runner = runner
        if value is not None:
            setattr(self, self._main_resource, value)
            self.bound = True
        else:
            self.bound = False

    def get_data(self, resource):
        return self._resource_data[resource]

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
            value = getattr(self, self._main_resource)
        else:
            value = 'unbound'
        return '<{} {}>'.format(type(self).__name__, value)

    @property
    def env(self):
        return self.runner.env


class Collection(Resource):
    def __init__(self, base_cls, value=None, runner=None):
        super(Collection, self).__init__(value, runner)
        self.base_cls = base_cls
        self.list_fn = None

    def list(self, fn):
        self.list_fn = fn
        return self

    __call__ = list

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
        return tasks.BoundTask(
            self.collection,
            CollectionUnboundTask(getattr(base_cls, name)),
        )


class CollectionUnboundTask(tasks.UnboundTask):
    def __init__(self, task):
        super(CollectionUnboundTask, self).__init__(task.fn, task.requires)
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
