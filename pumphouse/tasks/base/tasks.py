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
    wrapper = None

    def __init__(self, fn=None, name=None,
                 requires=[], after=[], before=[]):
        self._resource_task = {}
        if fn is not None and self.wrapper is not None:
            self.fn = self.wrapper(fn)
        else:
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
        if self.wrapper is not None:
            self.fn = self.wrapper(fn)
        else:
            self.fn = fn
        self.name = fn.__name__
        return self

    def __get__(self, instance, owner):
        if instance is None:
            return self
        if not instance.bound:
            return BoundTask(instance, self)
        else:
            return self.get_for_resource(instance)

    def get_for_resource(self, resource, realize=True):
        assert resource.bound
        try:
            return self._resource_task[resource]
        except KeyError:
            if not realize:
                return None
            task = self.realize_with(resource)
            self._resource_task[resource] = task
            return task

    def realize_with(self, resource):
        assert resource.bound
        requires = []
        for task in self.requires:
            requires.append(task.get_for_resource(resource))
        after = [(task, resource) for task in self.after]
        before = [(task, resource) for task in self.before]
        return Task(self.fn, self.name, resource,
                    requires=requires, after=after, before=before)

    def __repr__(self):
        return '<{} {}>'.format(
            type(self).__name__, self.name)


class BoundTask(object):
    def __init__(self, resource, unbound_task):
        self.resource = resource
        self.task = unbound_task

    def get_for_resource(self, resource, realize=True):
        bound_res = self.resource.get_bound_subres(resource)
        return self.task.get_for_resource(bound_res, realize=realize)

    def __repr__(self):
        return '<{} {} {}>'.format(
            type(self).__name__, self.task.name, self.resource)


class Task(object):
    def __init__(self, fn, name, resource, requires=[], after=[], before=[]):
        self.fn = fn
        self.name = name
        self.resource = resource
        self.requires = frozenset(requires)
        self.after = set(after)
        self.before = set(before)

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


def process_tasks(tasks):
    def get_tasks(task):
        for req_task in task.requires:
            for _task in get_tasks(req_task):
                yield _task
        yield task
    all_tasks = {}
    for task in tasks:
        for _task in get_tasks(task):
            if _task not in all_tasks:
                all_tasks[_task] = Task(_task.fn, _task.name, _task.resource)
    for old_task, new_task in all_tasks.iteritems():
        new_task.requires = set(all_tasks[task] for task in old_task.requires)
        for pretask, resource in old_task.after:
            real_task = pretask.get_for_resource(resource, realize=False)
            if real_task and real_task in all_tasks:
                new_real_task = all_tasks[real_task]
                new_real_task.before.add(new_task)
                new_task.after.add(new_real_task)
        for posttask, resource in old_task.before:
            real_task = posttask.get_for_resource(resource, realize=False)
            if real_task and real_task in all_tasks:
                new_real_task = all_tasks[real_task]
                new_real_task.after.add(new_task)
                new_task.before.add(new_real_task)
    for task in all_tasks.itervalues():
        yield task

task = UnboundTask
