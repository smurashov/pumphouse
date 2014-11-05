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

import functools

import taskflow.engines
from taskflow.patterns import graph_flow
import taskflow.task

from . import resources

__all__ = ['Runner', 'TaskflowRunner']


class Runner(object):
    def __init__(self, env=None):
        self.resources = {}
        self.tasks = set()
        self.env = env

    def get_resource(self, resource, data):
        id_ = resource.get_id_for(data)
        if isinstance(resource, resources.Collection):
            base_cls = resource.base_cls
            res_type = functools.partial(resources.Collection,
                                         base_cls=base_cls)
            key = (resources.Collection, base_cls, id_)
        else:
            if isinstance(resource, type(resources.Resource)):
                res_type = resource
            else:
                res_type = type(resource)
            key = (res_type, id_)
        try:
            return self.resources[key]
        except KeyError:
            res = res_type(data=data, runner=self)
            self.resources[key] = res
            return res

    def add(self, task):
        self.tasks.update(task.get_tasks())

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


def _make_str_id(id_):
    if isinstance(id_, tuple):
        return "-".join(map(_make_str_id, id_))
    elif isinstance(id_, frozenset):
        return "+".join(map(_make_str_id, sorted(id_)))
    elif isinstance(id_, type):
        return id_.__name__
    else:
        return id_


class TaskflowRunner(Runner):
    def get_task_name(self, task):
        id_ = _make_str_id(task.resource.get_id())
        return "_".join((type(task.resource).__name__, id_, task.name))

    def convert_task(self, task):
        name = self.get_task_name(task)
        flow_task = TaskFlowTask(
            task,
            name=name,
            provides=name,
            rebind=[self.get_task_name(req_task)
                    for req_task in (task.requires | task.after & self.tasks)],
        )
        return flow_task

    def run(self):
        flow = graph_flow.Flow("main flow")
        for task in self.tasks:
            flow.add(self.convert_task(task))
        taskflow.engines.run(flow, engine_conf='parallel')
