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

from taskflow.patterns import linear_flow, unordered_flow

# from pumphouse.tasks import hypervisor as hypervisor_tasks
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
    hostname_bind = "evacuate-{}".format(hostname)
    flow = linear_flow.Flow(hostname_bind)
    flow.add(service_tasks.DiableServiceWithRollback("nova-compute",
                                                     context.src_cloud,
                                                     name=hostname_bind,
                                                     rebind=[hostname_bind],
                                                     inject={
                                                         "hostname": hostname,
                                                     }))
    servers_flow = unordered_flow.Flow("evacuate-{}-servers".format(hostname))
    for hyperv in hypervs:
        if hasattr(hyperv, "servers"):
            for server in hyperv.servers:
                server_flow = server_tasks.evacuate_server(context,
                                                           server["uuid"])
                if server_flow is not None:
                    servers_flow.add(server_flow)
    flow.add(servers_flow)
    return flow
