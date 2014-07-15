import gevent
import logging

import flask

from . import evacuation
from . import hooks
from . import migration


LOG = logging.getLogger(__name__)

pump = flask.Blueprint("pumphouse", __name__)


def cloud_resources(cloud):
    def get_host_status(hostname):
        services = cloud.nova.services.list(host=hyperv.service["host"],
                                            binary="nova-compute")
        service = services[0]
        if service.state == "up":
            if service.status == "enabled":
                return "available"
            else:
                return "blocked"
        return "error"

    resources = {
        "tenants": [{
            "id": tenant.id,
            "name": tenant.name,
            "description": tenant.description,
        } for tenant in cloud.keystone.tenants.list()
        ],
        "resources": [{
            "id": server.id,
            "type": "server",
            "name": server.name,
            "status": server.status.lower(),
            "tenant_id": server.tenant_id,
            "image_id": server.image["id"],
            # TODO(akscram): Mapping of real hardware servers to
            #                hypervisors should be here.
            "host_name": getattr(server,
                                 "OS-EXT-SRV-ATTR:hypervisor_hostname"),
        } for server in cloud.nova.servers.list(search_opts={"all_tenants": 1})
        ] + [{
            "id": image["id"],
            "type": "image",
            "status": "",
            "name": image["name"],
        } for image in cloud.glance.images.list()
        ],
        "hosts": [{
            "name": hyperv.service["host"],
            "status": get_host_status(hyperv.service["host"]),
        } for hyperv in cloud.nova.hypervisors.list()
        ],
    }
    return resources


@pump.route("/")
def index():
    filename = "{}/static/index.html".format(
        flask.current_app.config.root_path)
    return flask.send_file(filename)


@pump.route("/resources")
def resources():
    return flask.jsonify(
        source=cloud_resources(hooks.source.client),
        destination=cloud_resources(hooks.destination.client),
        # TODO(akscram): A set of hosts that don't belong to any cloud.
        hosts=[],
        # TODO(akscram): A set of current events.
        events=[],
    )


@pump.route("/tenants/<tenant_id>", methods=["POST"])
def migrate_tenant(tenant_id):
    @flask.copy_current_request_context
    def migrate():
        migration.migrate_resources(tenant_id)
    gevent.spawn(migrate)
    return flask.make_response()


@pump.route("/hosts/<host_name>", methods=["POST"])
def evacuate_host(host_name):
    @flask.copy_current_request_context
    def evacuate():
        evacuation.evacuate_servers(host_name)
    gevent.spawn(evacuate)
    return flask.make_response()


# XXX(akscram): Nothing works without this.
@hooks.events.on("connect", namespace="/events")
def handle_events_connection():
    LOG.debug("Client connected to '/events'.")
