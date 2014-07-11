import logging

from novaclient import exceptions as nova_excs

from . import hooks
from pumphouse import utils


LOG = logging.getLogger(__name__)


def evacuate_servers(hostname):
    events, cloud = hooks.events, hooks.source
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
