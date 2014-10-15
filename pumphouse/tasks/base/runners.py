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
        self.tasks = []
        self.env = env

    def get_resource(self, resource, data):
        if isinstance(resource, resources.Collection):
            base_cls = resource.base_cls
            res_type = functools.partial(resources.Collection,
                                         base_cls=base_cls)
            key = (resources.Collection, base_cls, resource.get_id_for(data))
        else:
            if isinstance(resource, type(resources.Resource)):
                res_type = resource
            else:
                res_type = type(resource)
            key = (res_type, res_type.get_id_for(data))
        try:
            return self.resources[key]
        except KeyError:
            res = res_type(value=data, runner=self)
            self.resources[key] = res
            return res

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
