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
import logging
import pdb
import traceback

import taskflow.engines
from taskflow.patterns import graph_flow
import taskflow.task

from . import resources
from . import tasks

__all__ = ['Runner', 'TaskflowRunner']

LOG = logging.getLogger(__name__)


class Runner(object):
    def __init__(self, env=None):
        self.resources = {}
        self.tasks = set()
        self.env = env

    def get_resource(self, resource, data, context=None):
        id_ = resource.get_id_for_runner(data, context, self)
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
            res = res_type(data=data, context=context, runner=self)
            self.resources[key] = res
            return res

    def add(self, task):
        self.tasks.add(task)

    def run(self):
        print("Hey, I'm gonna run these tasks:")
        print("\n".join(map(repr, self.tasks)))


class TaskFlowTask(taskflow.task.Task):
    def __init__(self, task, post_mortem, **kwargs):
        super(TaskFlowTask, self).__init__(**kwargs)
        self.task = task
        self.post_mortem = post_mortem

    def execute(self, **dependencies):
        logargs = self.task.name, self.task.resource
        if self.task.fn is not None:
            LOG.debug("Starting task %s of %s", *logargs)
            try:
                self.task.fn(self.task.resource)
            except Exception:
                if self.post_mortem:
                    traceback.print_exc()
                    pdb.post_mortem()
                raise
            LOG.debug("Finished task %s of %s", *logargs)
        else:
            LOG.debug("Passed empty task %s of %s", *logargs)


def _make_str_id(id_):
    if isinstance(id_, tuple):
        return "-".join(map(_make_str_id, id_))
    elif isinstance(id_, frozenset):
        return "+".join(map(_make_str_id, sorted(id_)))
    elif isinstance(id_, type):
        return id_.__name__
    elif id_ is None:
        return "__NULL__"
    else:
        return id_


class TaskflowRunner(Runner):
    def __init__(self, env):
        super(TaskflowRunner, self).__init__(env)
        try:
            self.post_mortem = env.plugins["post_mortem"]
        except (AttributeError, KeyError):
            self.post_mortem = False

    def get_task_name(self, task):
        id_ = _make_str_id(task.resource.get_id())
        return "_".join((type(task.resource).__name__, id_, task.name))

    def convert_task(self, task):
        name = self.get_task_name(task)
        flow_task = TaskFlowTask(
            task,
            post_mortem=self.post_mortem,
            name=name,
            provides=name,
            rebind=map(self.get_task_name, task.requires | task.after),
        )
        return flow_task

    def create_flow(self):
        flow = graph_flow.Flow("main flow")
        for task in tasks.process_tasks(self.tasks):
            flow.add(self.convert_task(task))
        return flow

    def run(self):
        taskflow.engines.run(self.create_flow(), engine_conf='parallel')
