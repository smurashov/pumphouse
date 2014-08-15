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

from novaclient import exceptions as nova_excs

from pumphouse import utils


LOG = logging.getLogger(__name__)


def evacuate_servers(events, cloud, hostname):
    try:
        hypervs = cloud.nova.hypervisors.search(hostname, servers=True)
    except nova_excs.NotFound:
        LOG.exception("Could not find hypervisors at the host %r.", hostname)
    else:
        if len(hypervs) > 1:
            LOG.warning("More than one hypervisor found at the host: %s",
                        hostname)
        events.emit("host evacuation", {"name": hostname}, namespace="/events")
        cloud.nova.services.disable(hostname, "nova-compute")
        events.emit("host block", {"name": hostname}, namespace="/events")
        for hyperv in hypervs:
            try:
                for server in hyperv.servers:
                    server_id = server["uuid"]
                    events.emit("server live migration", {"id": server_id},
                                namespace="/events")
                    cloud.nova.servers.live_migrate(server_id, None,
                                                    True, False)
                    server = utils.wait_for(server_id, cloud.nova.servers.get,
                                            value="ACTIVE")
                    hostname_attr = "OS-EXT-SRV-ATTR:hypervisor_hostname"
                    dst_hostname = getattr(server, hostname_attr)
                    events.emit("server live migrated", {
                        "id": server.id,
                        "host_name": dst_hostname,
                    }, namespace="/events")
            except Exception:
                LOG.exception("An error occured during evacuation servers "
                              "from the host %r", hostname)
                cloud.nova.services.enable(hostname, "nova-compute")
        events.emit("host evacuated", {"name": hostname}, namespace="/events")
