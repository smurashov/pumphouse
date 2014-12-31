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

import taskflow.task

from pumphouse import events
from pumphouse import task
from pumphouse import utils


LOG = logging.getLogger(__name__)


class ServiceTask(task.BaseCloudTask):
    def __init__(self, *args, **kwargs):
        self.client = kwargs.pop("client", "nova")
        super(ServiceTask, self).__init__(*args, **kwargs)

    def get_client(self):
        if self.client == "nova":
            return self.cloud.nova
        elif self.client == "cinder":
            return self.cloud.cinder


class RetrieveServices(ServiceTask):
    def execute(self):
        services = dict((s.id, s.to_dict())
                        for s in self.get_client().services.list())
        return services


class DisableService(ServiceTask):
    def __init__(self, binary, *args, **kwargs):
        super(DisableService, self).__init__(*args, **kwargs)
        self.binary = binary

    def execute(self, hostname):
        self.get_client().services.disable(hostname, self.binary)
        self.block_event(hostname)

    def block_event(self, hostname):
        LOG.info("Service %r was blocked on host %r", self.binary, hostname)
        events.emit("update", {
            "id": hostname,
            "type": "host",
            "cloud": self.cloud.name,
            "data": {
                "status": "blocked",
            }
        }, namespace="/events")


class DiableServiceWithRollback(DisableService):
    def revert(self, hostname, result, flow_failures):
        self.get_client().services.enable(hostname, self.binary)
        self.unblock_event(hostname)

    def unblock_event(self, hostname):
        LOG.info("Service %r was unblocked on host %r",
                 self.binary, hostname)
        events.emit("update", {
            "id": hostname,
            "type": "host",
            "cloud": self.cloud.name,
            "data": {
                "status": "available",
            }
        }, namespace="/events")


class DeleteServicesSilently(ServiceTask):
    def execute(self, hostname):
        services = []
        for service in self.get_client().services.list(host=hostname):
            try:
                self.get_client().services.delete(service.id)
            except Exception:
                LOG.exception("Error occurred during deleting of the service "
                              "%s/%s", service.host, service.binary)
            else:
                services.append(service.to_dict())
        return services


class WaitComputesServices(ServiceTask):
    def execute(self, hostname, **requires):
        hypervisors = utils.wait_for(hostname,
                                     self.get_hypervisors,
                                     attribute_getter=bool,
                                     value=True)
        return hypervisors

    def get_hypervisors(self, hostname):
        hypervisors = []
        services = self.get_client().services.list(host=hostname,
                                                 binary="nova-compute")
        for s in services:
            if s.state == "up" and s.status == "enabled":
                hypervisors.append(s.to_dict())
            else:
                return False
        return hypervisors


class GetService(taskflow.task.Task):
    def execute(self, services, service_id):
        return services[service_id]


class GetServiceHostname(taskflow.task.Task):
    def execute(self, service_info):
        return service_info["host"]


def get_hostname(context, flow, service_id):
    hostname = "hostname-{}".format(service_id)
    services = "services-{}".format(service_id)
    service = "service-{}".format(service_id)

    flow.add(
        RetrieveServices(context.src_cloud,
                         name=services,
                         provides=services),
        GetService(name=service,
                   provides=service,
                   rebind=[services],
                   inject={"service_id": int(service_id)}),
        GetServiceHostname(name=hostname,
                           provides=hostname,
                           rebind=[service]),
    )
