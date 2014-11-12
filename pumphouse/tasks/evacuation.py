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

from taskflow.patterns import graph_flow

from pumphouse import exceptions
from pumphouse.tasks import server as server_tasks
from pumphouse.tasks import service as service_tasks


LOG = logging.getLogger(__name__)


def evacuate_servers(context, hostname):
    try:
        hypervs = context.src_cloud.nova.hypervisors.search(hostname,
                                                            servers=True)
    except exceptions.nova_excs.NotFound:
        LOG.exception("Could not find hypervisors at the host %r.", hostname)
        raise

    disable_services = "disable-services-{}".format(hostname)
    flow = graph_flow.Flow(disable_services)
    flow.add(service_tasks.DiableServiceWithRollback("nova-compute",
                                                     context.src_cloud,
                                                     name=disable_services,
                                                     provides=disable_services,
                                                     inject={
                                                         "hostname": hostname,
                                                     }))
    for hyperv in hypervs:
        if hasattr(hyperv, "servers"):
            for server in hyperv.servers:
                server_tasks.evacuate_server(context, flow, server["uuid"],
                                             requires=[disable_services])
    return flow
