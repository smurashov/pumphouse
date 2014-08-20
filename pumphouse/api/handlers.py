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
import logging

import flask

from . import evacuation
from . import hooks
from pumphouse import flows
from pumphouse.tasks import identity as identity_tasks


LOG = logging.getLogger(__name__)

pump = flask.Blueprint("pumphouse", __name__)


def crossdomain(origin=None, methods=None, headers=None,
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


@pump.route("/reset", methods=["POST"])
def reset():
    reset = flask.current_app.config["CLOUDS_RESET"]
    if not reset:
        return flask.make_response("", 404)

    @flask.copy_current_request_context
    def reset_source():
        hooks.source.reset(hooks.events)

    @flask.copy_current_request_context
    def reset_destination():
        hooks.destination.reset(hooks.events)
    gevent.spawn(reset_destination)
    gevent.spawn(reset_source)
    return flask.make_response("", 201)


@pump.route("/resources")
@crossdomain(origin='*.mirantis.com')
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
def migrate_tenant(tenant_id):
    @flask.copy_current_request_context
    def migrate():
        # FIXME(akscram): The params don't support yet.
        # parameters = flask.current_app.config.get("PARAMETERS")
        src = hooks.source.connect()
        dst = hooks.destination.connect()
        store = {}
        identity_flow, store = identity_tasks.migrate_identity(src, dst, store,
                                                               tenant_id)
        LOG.debug("Migration flow: %s", identity_flow)
        result = flows.run_flow(identity_flow, store)
        LOG.info("Result of migration: %s", result)
    gevent.spawn(migrate)
    return flask.make_response()


@pump.route("/hosts/<host_name>", methods=["POST"])
def evacuate_host(host_name):
    @flask.copy_current_request_context
    def evacuate():
        source = hooks.source.connect()
        evacuation.evacuate_servers(hooks.events, source, host_name)
    gevent.spawn(evacuate)
    return flask.make_response()


# XXX(akscram): Nothing works without this.
@hooks.events.on("connect", namespace="/events")
def handle_events_connection():
    LOG.debug("Client connected to '/events'.")
