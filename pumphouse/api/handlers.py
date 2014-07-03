import flask

from .hooks import source, destination


pump = flask.Blueprint("pumphouse", __name__)


def cloud_resources(cloud):
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
            "name": image["name"],
        } for image in cloud.glance.images.list()
        ],
        "hosts": [{
            "name": hyperv.service["host"],
            "status": "available"
                      if cloud.nova.services.list(
                            host=hyperv.service["host"],
                            binary="nova-compute")[0].state
                      else "unavailable",
        } for hyperv in cloud.nova.hypervisors.list()
        ],
    }
    return resources


@pump.route("/resources")
def resources():
    src_resources = cloud_resources(source)
    dst_resources = cloud_resources(destination)
    return flask.jsonify(
        source=cloud_resources(source),
        destination=cloud_resources(destination),
        # TODO(akscram): A set of hosts that don't belong to any cloud.
        hosts=[],
        # TODO(akscram): A set of current events.
        events=[],
    )


@pump.route("/events")
def events():
    return "events"
