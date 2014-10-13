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


from pumphouse import events
from pumphouse import task


LOG = logging.getLogger(__name__)


class DisableService(task.BaseCloudTask):
    def __init__(self, binary, *args, **kwargs):
        super(DisableService, self).__init__(*args, **kwargs)
        self.binary = binary

    def execute(self, hostname):
        self.cloud.nova.services.disable(hostname, self.binary)
        self.block_event(hostname)

    def revert(self, hostname, result, flow_failures):
        self.cloud.nova.services.enable(hostname, self.binary)
        self.unblock_event(hostname)

    def block_event(self, hostname):
        LOG.info("Service %r was blocked on host %r", self.binary, hostname)
        events.emit("host block", {
            "name": hostname,
            "cloud": self.cloud.name,
        }, namespace="/events")

    def unblock_event(self, hostname):
        LOG.info("Service %r was unblocked on host %r",
                 self.binary, hostname)
        events.emit("host unblock", {
            "name": hostname,
            "cloud": self.cloud.name,
        }, namespace="/events")
