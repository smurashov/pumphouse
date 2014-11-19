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


def cloud_resources(cloud):
    for tenant in cloud.keystone.tenants.list():
        yield {
            "id": tenant.id,
            "cloud": cloud.name,
            "type": "tenant",
            "data": {
                "id": tenant.id,
                "name": tenant.name,
                "description": tenant.description,
            },
        }
    for server in cloud.nova.servers.list(search_opts={"all_tenants": 1}):
        yield {
            "id": server.id,
            "cloud": cloud.name,
            "type": "server",
            "data": {
                "id": server.id,
                "name": server.name,
                "status": server.status,
                "tenant_id": server.tenant_id,
                "image_id": server.image["id"],
                # TODO(akscram): Mapping of real hardware servers to
                #                hypervisors should be here.
                "host_id": getattr(server,
                                   "OS-EXT-SRV-ATTR:hypervisor_hostname"),
            },
        }
    for volume in cloud.cinder.volumes.list(search_opts={"all_tenants": 1}):
        attachments = [attachment["server_id"]
                       for attachment in volume.attachments]
        yield {
            "id": volume.id,
            "cloud": cloud.name,
            "type": "volume",
            "data": {
                "id": volume.id,
                "status": volume.status.lower(),
                "display_name": volume.display_name,
                "tenant_id": getattr(volume, "os-vol-tenant-attr:tenant_id"),
                "attachment_server_ids": attachments,
            },
        }
    for image in cloud.glance.images.list():
        yield {
            "id": image["id"],
            "cloud": cloud.name,
            "type": "image",
            "data": {
                "id": image["id"],
                "status": "",
                "name": image["name"],
            },
        }
    for floating_ip in cloud.nova.floating_ips_bulk.list():
        yield {
            "id": floating_ip.address,
            "cloud": cloud.name,
            "type": "floating_ip",
            "data": {
                "name": floating_ip.address,
                "server_id": floating_ip.instance_uuid,
            }
        }
    for hyperv in cloud.nova.hypervisors.list():
        services = cloud.nova.services.list(host=hyperv.service["host"],
                                            binary="nova-compute")
        service = services[0]
        if service.state == "up":
            if service.status == "enabled":
                status = "available"
            else:
                status = "blocked"
        else:
            status = "error"
        yield {
            "id": hyperv.service["host"],
            "cloud": cloud.name,
            "type": "host",
            "data": {
                "name": hyperv.service["host"],
                "status": status,
            },
        }


def cloud_view(client):
    return {
        "urls": client.cloud_urls,
        "resources": list(cloud_resources(client.connect())),
    }


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
        source=cloud_view(hooks.source),
        destination=cloud_view(hooks.destination),
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
        events.emit("update", {
            "id": tenant_id,
            "cloud": src.name,
            "type": "tenant",
            "progress": None,
            "action": "migration",
        }, namespace="/events")

        try:
            flow = resource_tasks.migrate_resources(ctx, tenant_id)
            LOG.debug("Migration flow: %s", flow)
            result = flows.run_flow(flow, ctx.store)
            LOG.debug("Result of migration: %s", result)
        except Exception:
            msg = ("Error is occured during migration resources of tenant: {}"
                   .format(tenant_id))
            LOG.exception(msg)
            events.emit("error", {
                "message": msg,
            }, namespace="/events")

        events.emit("update", {
            "id": tenant_id,
            "cloud": src.name,
            "type": "tenant",
            "progress": None,
            "action": None,
        }, namespace="/events")

    gevent.spawn(migrate)
    return flask.make_response()


@pump.route("/hosts/<host_id>", methods=["POST"])
@crossdomain()
def evacuate_host(host_id):
    @flask.copy_current_request_context
    def evacuate():
        config = flask.current_app.config.get("PLUGINS") or {}
        src = hooks.source.connect()
        dst = hooks.destination.connect()
        ctx = context.Context(config, src, dst)
        events.emit("update", {
            "id": host_id,
            "type": "host",
            "cloud": src.name,
            "progress": None,
            "action": "evacuation",
        }, namespace="/events")

        try:
            flow = evacuation.evacuate_servers(ctx, host_id)
            LOG.debug("Evacuation flow: %s", flow)
            result = flows.run_flow(flow, ctx.store)
            LOG.debug("Result of evacuation: %s", result)
        except Exception:
            msg = ("Error is occured during evacuating host {}"
                   .format(host_id))
            LOG.exception(msg)
            events.emit("error", {
                "message": msg,
            }, namespace="/events")

        events.emit("update", {
            "id": host_id,
            "type": "host",
            "cloud": src.name,
            "progress": None,
            "action": None,
        }, namespace="/events")
    gevent.spawn(evacuate)
    return flask.make_response()


@pump.route("/hosts/<host_id>", methods=["DELETE"])
@crossdomain()
def reassign_host(host_id):
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

        try:
            src = hooks.source.connect()
            dst = hooks.destination.connect()
            ctx = context.Context(config, src, dst)

            flow = node_tasks.reassign_node(ctx, host_id)
            LOG.debug("Reassigning flow: %s", flow)
            result = flows.run_flow(flow, ctx.store)
            LOG.debug("Result of migration: %s", result)
        except Exception:
            msg = ("Error is occured during reassigning host {}"
                   .format(host_id))
            LOG.exception(msg)
            events.emit("error", {
                "message": msg,
            }, namespace="/events")

    gevent.spawn(reassign)
    return flask.make_response()


# XXX(akscram): Nothing works without this.
@events.on("connect", namespace="/events")
def handle_events_connection():
    LOG.debug("Client connected to '/events'.")
