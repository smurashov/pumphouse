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

from . import resources
from . import tasks

__all__ = ["Plugin"]


class MemoSet(object):
    def __init__(self):
        self.items = set()

    def __contains__(self, item):
        self.items.add(item)
        return True
    add = __contains__


class Plugin(resources.Resource):
    class __metaclass__(resources.Resource.__metaclass__):
        def __new__(mcs, name, bases, cls_vars):
            res = resources.Resource.__metaclass__.__new__(mcs, name, bases,
                                                           cls_vars)
            res._implementations = {}
            res._tasks = MemoSet()
            res._unbound_tasks = {}
            return res

        def __getattr__(cls, name):
            try:
                return cls._unbound_tasks[name]
            except KeyError:
                cls._tasks.add(name)
                task = PluginUnboundTask(name, cls)
                cls._unbound_tasks[name] = task
                return task

    @classmethod
    def register(cls, name):
        def __inner(impl):
            cls._implementations[name] = impl
            return impl
        return __inner

    @classmethod
    def get_impl(cls, runner):
        plugin = runner.env.plugins.get(cls.plugin_key, cls.default)
        impl = cls._implementations[plugin]
        assert set(impl._tasks) >= cls._tasks.items
        return impl

    def __new__(cls, data=None, runner=None):
        if data is not None:
            return runner.get_resource(cls.get_impl(runner), data)
        else:
            return super(Plugin, cls).__new__(cls, data=data, runner=runner)

    def __getattr__(self, name):
        unbound_task = getattr(type(self), name)
        return unbound_task.__get__(self, type(self))

    @classmethod
    def get_id_for_runner(cls, data, runner):
        return cls.get_impl(runner).get_id_for_runner(data, runner)


class PluginUnboundTask(tasks.UnboundTask):
    def __init__(self, name, plugin):
        super(PluginUnboundTask, self).__init__(name=name)
        self.plugin = plugin

    def realize_with(self, resource):
        impl = self.plugin.get_impl(resource.get_runner())
        task = getattr(impl, self.name)
        return task.get_for_resource(resource)
