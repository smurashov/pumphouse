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

import datetime
import functools
import gevent
import os
import logging

import flask

from . import hooks

from pumphouse import context
from pumphouse import events
from pumphouse import flows
from pumphouse.tasks import evacuation
from pumphouse.tasks import resources as resource_tasks
from pumphouse.tasks import node as node_tasks


LOG = logging.getLogger(__name__)

pump = flask.Blueprint("pumphouse", __name__)


def crossdomain(origin='*', methods=None, headers=('Accept', 'Content-Type'),
                max_age=21600, attach_to_all=True,
                automatic_options=True):
    if methods is not None:
        methods = ', '.join(sorted(x.upper() for x in methods))
    if headers is not None and not isinstance(headers, basestring):
        headers = ', '.join(x.upper() for x in headers)
    if not isinstance(origin, basestring):
        origin = ', '.join(origin)
    if isinstance(max_age, datetime.timedelta):
        max_age = max_age.total_seconds()

    def get_methods():
        if methods is not None:
            return methods

        options_resp = flask.current_app.make_default_options_response()
        return options_resp.headers['allow']

    def decorator(f):
        def wrapped_function(*args, **kwargs):
            if automatic_options and flask.request.method == 'OPTIONS':
                resp = flask.current_app.make_default_options_response()
            else:
                resp = flask.make_response(f(*args, **kwargs))
            if not attach_to_all and flask.request.method != 'OPTIONS':
                return resp

            h = resp.headers

            h['Access-Control-Allow-Origin'] = origin
            h['Access-Control-Allow-Methods'] = get_methods()
            h['Access-Control-Max-Age'] = str(max_age)
            if headers is not None:
                h['Access-Control-Allow-Headers'] = headers
            return resp

        f.provide_automatic_options = False
        f.required_methods = ['OPTIONS']
        return functools.update_wrapper(wrapped_function, f)
    return decorator


def cloud_resources(client):
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

    cloud = client.connect()
    resources = {
        "urls": client.cloud_urls,
        "tenants": [{
            "id": tenant.id,
            "name": tenant.name,
            "description": tenant.description,
        } for tenant in cloud.keystone.tenants.list()
        ],
        "servers": [{
            "id": server.id,
            "name": server.name,
            "status": server.status.lower(),
            "tenant_id": server.tenant_id,
            "image_id": server.image["id"],
            # TODO(akscram): Mapping of real hardware servers to
            #                hypervisors should be here.
            "host_name": getattr(server,
                                 "OS-EXT-SRV-ATTR:hypervisor_hostname"),
        } for server in cloud.nova.servers.list(search_opts={"all_tenants": 1})
        ],
        "images": [{
            "id": image["id"],
            "status": "",
            "name": image["name"],
        } for image in cloud.glance.images.list()
        ],
        "floating_ips": [{
            "id": floating_ip.address,
            "server_id": floating_ip.instance_uuid
        } for floating_ip in cloud.nova.floating_ips_bulk.list()
        ],
        "hosts": [{
            "name": hyperv.service["host"],
            "status": get_host_status(hyperv.service["host"]),
        } for hyperv in cloud.nova.hypervisors.list()
        ]
    }
    return resources


@pump.route("/")
def index():
    filename = "{}/static/index.html".format(
        flask.current_app.config.root_path)
    return flask.send_file(filename)


@pump.route("/reset", methods=["POST"])
@crossdomain()
def reset():
    reset = flask.current_app.config["CLOUDS_RESET"]
    if not reset:
        return flask.make_response("", 404)

    @flask.copy_current_request_context
    def reset_source():
        hooks.source.reset(events)

    @flask.copy_current_request_context
    def reset_destination():
        hooks.destination.reset(events)

    gevent.spawn(reset_destination)
    gevent.spawn(reset_source)

    events.emit("reset start", {
    }, namespace="/events")

    return flask.make_response("", 201)


@pump.route("/resources")
@crossdomain()
def resources():
    return flask.jsonify(
        reset=flask.current_app.config["CLOUDS_RESET"],
        source=cloud_resources(hooks.source),
        destination=cloud_resources(hooks.destination),
        # TODO(akscram): A set of hosts that don't belong to any cloud.
        hosts=[],
        # TODO(akscram): A set of current events.
        events=[],
    )


@pump.route("/tenants/<tenant_id>", methods=["POST"])
@crossdomain()
def migrate_tenant(tenant_id):
    @flask.copy_current_request_context
    def migrate():
        config = flask.current_app.config.get("PLUGINS") or {}
        src = hooks.source.connect()
        dst = hooks.destination.connect()
        ctx = context.Context(config, src, dst)
        events.emit("tenant migrate", {
            "id": tenant_id
        }, namespace="/events")

        try:
            flow = resource_tasks.migrate_resources(ctx, tenant_id)
            LOG.debug("Migration flow: %s", flow)
            result = flows.run_flow(flow, ctx.store)
            LOG.debug("Result of migration: %s", result)
            # TODO(akcram): All users' passwords should be restored when all
            #               migration operations ended.
        except Exception:
            LOG.exception("Error is occured during migration resources of "
                          "tenant: %s", tenant_id)
            status = "error"
        else:
            status = ""

        events.emit("tenant migrated", {
            "id": tenant_id,
            "status": status
        }, namespace="/events")

    gevent.spawn(migrate)
    return flask.make_response()


@pump.route("/hosts/<hostname>", methods=["POST"])
@crossdomain()
def evacuate_host(hostname):
    @flask.copy_current_request_context
    def evacuate():
        config = flask.current_app.config.get("PLUGINS") or {}
        src = hooks.source.connect()
        dst = hooks.destination.connect()
        ctx = context.Context(config, src, dst)
        events.emit("host evacuate", {
            "id": hostname,
        }, namespace="/events")

        try:
            flow = evacuation.evacuate_servers(ctx, hostname)
            LOG.debug("Evacuation flow: %s", flow)
            result = flows.run_flow(flow, ctx.store)
            LOG.debug("Result of evacuation: %s", result)
        except Exception:
            LOG.exception("Error is occured during evacuating host %r",
                          hostname)
            status = "error"
        else:
            status = ""

        events.emit("host evacuated", {
            "id": hostname,
            "status": status,
        }, namespace="/events")
    gevent.spawn(evacuate)
    return flask.make_response()


@pump.route("/hosts/<hostname>", methods=["DELETE"])
@crossdomain()
def reassign_host(hostname):
    @flask.copy_current_request_context
    def reassign():
        # NOTE(akscram): Initialization of fuelclient.
        fuel_config = flask.current_app.config["CLOUDS"]["fuel"]["endpoint"]
        os.environ["SERVER_ADDRESS"] = fuel_config["host"]
        os.environ["LISTEN_PORT"] = str(fuel_config["port"])
        os.environ["KEYSTONE_USER"] = fuel_config["username"]
        os.environ["KEYSTONE_PASS"] = fuel_config["password"]

        src_config = hooks.source.config()
        dst_config = hooks.destination.config()
        config = {
            "source": src_config["environment"],
            "destination": dst_config["environment"],
        }
        ctx = context.Context(config, None, None)
        events.emit("host reassign", {
            "id": hostname,
        }, namespace="/events")

        try:
            flow = node_tasks.reassign_node(ctx, hostname)
            LOG.debug("Reassigning flow: %s", flow)
            result = flows.run_flow(flow, ctx.store)
            LOG.debug("Result of migration: %s", result)
        except Exception:
            LOG.exception("Error is occured during reassigning host %r",
                          hostname)
            status = "error"
        else:
            status = ""

        events.emit("host reassigned", {
            "id": hostname,
            "status": status,
        }, namespace="/events")
    gevent.spawn(reassign)
    return flask.make_response()


# XXX(akscram): Nothing works without this.
@events.on("connect", namespace="/events")
def handle_events_connection():
    LOG.debug("Client connected to '/events'.")
