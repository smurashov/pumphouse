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

__all__ = ['UnboundTask', 'Task', 'task']


class UnboundTask(object):
    def __init__(self, fn=None, name=None,
                 requires=[], after=[], before=[]):
        self._resource_task = {}
        self.fn = fn
        if name is None and fn is not None:
            self.name = fn.__name__
        else:
            self.name = name
        self.requires = frozenset(requires)
        self.after = frozenset(after)
        self.before = frozenset(before)

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
        assert resource.bound
        try:
            return self._resource_task[resource]
        except KeyError:
            task = self.realize_with(resource)
            self._resource_task[resource] = task
            return task

    def realize_with(self, resource):
        assert resource.bound
        requires = []
        for task in self.requires:
            requires.append(task.get_for_resource(resource))
        after = []
        for task in self.after:
            after.append(task.get_for_resource(resource))
        before = []
        for task in self.before:
            before.append(task.get_for_resource(resource))
        res = Task(self.fn, self.name, resource,
                   requires=requires, after=after, before=before)
        for task in before:
            task.add_after(res)
        for task in after:
            task.add_before(res)
        return res


class BoundTask(object):
    def __init__(self, resource, unbound_task):
        self.resource = resource
        self.task = unbound_task

    def get_for_bound_resource(self, resource):
        return self.task.get_for_bound_resource(resource)

    def get_for_resource(self, resource):
        runner = resource.runner
        data = self.resource.get_data(resource)
        bound_res = runner.get_resource(self.resource, data)
        return self.get_for_bound_resource(bound_res)

    def __repr__(self):
        return '<{} {} {}>'.format(
            type(self).__name__, self.task.name, self.resource)


class Task(object):
    def __init__(self, fn, name, resource, requires, after=[], before=[]):
        self.fn = fn
        self.name = name
        self.resource = resource
        self.requires = frozenset(requires)
        self.after = set(after)
        self.before = set(before)

    def add_before(self, task):
        self.before.add(task)

    def add_after(self, task):
        if task not in self.requires:
            self.after.add(task)

    def get_tasks(self):
        for task in self.requires:
            for _task in task.get_tasks():
                yield _task
        yield self

    def __repr__(self):
        requires = ''
        if self.requires:
            requires += ' requires={}'.format(self.requires)
        if self.after:
            requires += ' after={}'.format(self.after)
        if self.before:
            requires += ' before={}'.format(self.before)
        return '<{} {} {}{}>'.format(
            type(self).__name__,
            self.name,
            self.resource,
            requires,
        )

task = UnboundTask
