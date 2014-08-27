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

import logging

from taskflow import task


LOG = logging.getLogger(__name__)


class SyncPoint(task.Task):
    def execute(self, **requires):
        targets = ",".join(requires.keys())
        LOG.debug("Point %s is synchronized with requirements: %s",
                  self.name, targets)


class UploadReporter(object):
    def __init__(self, context, size=0, period=0.1):
        self.context = context
        self.size = size
        self.period = period
        self.step_size = self.size * self.period
        self.last_step = 0
        self.uploaded = 0.0

    def set_size(self, size):
        self.size = size
        self.step_size = self.size * self.period

    def update(self, chunk):
        self.uploaded += chunk
        steps = int((self.uploaded - self.last_step) / self.step_size)
        if steps > 0:
            self.last_step += steps * self.step_size
            self.report(self.uploaded / self.size)

    def report(self, absolute):
        raise NotImplementedError()


class FileProxy(object):
    def __init__(self, data, reporter):
        # NOTE(akscram): The glance.images.data returns
        #                ResponseBodyIterator that wraps http response
        #                and provides an iterable object.
        self.resp = data._resp
        self.reporter = reporter
        data_size = int(data._resp.getheader("content-length", 0))
        self.reporter.set_size(data_size)

    def close(self):
        self.resp.close()

    def isclosed(self):
        return self.resp.isclosed()

    def read(self, amt=None):
        data = self.resp.read(amt)
        if data:
            self.reporter.update(len(data))
        return data
