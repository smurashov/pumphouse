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

import argparse
import collections
import logging
import os

from pumphouse import exceptions
from pumphouse import utils
from pumphouse import flows
from pumphouse import context
from pumphouse.tasks import base as tasks_base
from pumphouse.tasks import evacuation as evacuation_tasks
from pumphouse.tasks import image as image_tasks
from pumphouse.tasks import identity as identity_tasks
from pumphouse.tasks import resources as resources_tasks
from pumphouse.tasks import volume_resources as volume_tasks
from pumphouse.tasks import node as reassignment_tasks
from pumphouse.tasks import reset as reset_tasks

from taskflow.patterns import graph_flow
from taskflow.patterns import unordered_flow


LOG = logging.getLogger(__name__)

SERVICE_TENANT_NAME = 'services'
BUILTIN_ROLES = ('service', 'admin', '_member_')


def load_cloud_driver(is_fake=False):
    if is_fake:
        import_path = "pumphouse.fake.{}"
    else:
        import_path = "pumphouse.cloud.{}"
    cloud_driver = utils.load_class(import_path.format("Cloud"))
    identity_driver = utils.load_class(import_path.format("Identity"))
    return cloud_driver, identity_driver


def get_parser():
    parser = argparse.ArgumentParser(description="Migration resources through "
                                                 "OpenStack clouds.")
    parser.add_argument("config",
                        type=utils.safe_load_yaml,
                        help="A filename of a configuration of clouds "
                             "endpoints and a strategy.")
    parser.add_argument("--fake",
                        action="store_true",
                        help="Work with FakeCloud back-end instead real "
                             "back-end from config.yaml")
    parser.add_argument("--dump",
                        nargs="?",
                        const="flow.dot",
                        help="Dump flow without execution")

    subparsers = parser.add_subparsers()
    migrate_parser = subparsers.add_parser("migrate",
                                           help="Perform a migration of "
                                                "resources from a source "
                                                "cloud to a distination.")
    migrate_parser.set_defaults(action="migrate")
    migrate_parser.add_argument("--setup",
                                action="store_true",
                                help="If present, will add test resources to "
                                     "the source cloud before starting "
                                     "migration, as 'setup' command "
                                     "would do.")
    migrate_parser.add_argument("--num-tenants",
                                default='2',
                                type=int,
                                help="Number of tenants to create on setup.")
    migrate_parser.add_argument("--num-servers",
                                default='1',
                                type=int,
                                help="Number of servers per tenant to create "
                                "on setup.")
    migrate_parser.add_argument("--num-volumes",
                                default='1',
                                type=int,
                                help="Number of volumes per tenant to create "
                                "on setup.")
    migrate_parser.add_argument("resource",
                                choices=RESOURCES_MIGRATIONS.keys(),
                                nargs="?",
                                default="servers",
                                help="Specify a type of resources to migrate "
                                     "to the destination cloud.")
    migrate_filter = migrate_parser.add_mutually_exclusive_group(
        required=True)
    migrate_filter.add_argument("-i", "--ids",
                                nargs="*",
                                help="A list of IDs of resource to migrate to "
                                     "the destination cloud.")
    migrate_filter.add_argument("-t", "--tenant",
                                default=None,
                                help="Specify ID of a tenant which should be "
                                     "moved to destination cloud with all "
                                     "it's resources.")
    migrate_filter.add_argument("--host",
                                default=None,
                                help="Specify hypervisor hostname to filter "
                                     "servers designated for migration.")
    cleanup_parser = subparsers.add_parser("cleanup",
                                           help="Remove resources from a "
                                                "destination cloud.")
    cleanup_parser.set_defaults(action="cleanup")
    cleanup_parser.add_argument("target",
                                nargs="?",
                                choices=("source", "destination"),
                                default="destination",
                                help="Choose a cloud to clean up.")
    setup_parser = subparsers.add_parser("setup",
                                         help="Create resource in a source "
                                              "cloud for the test purposes.")
    setup_parser.set_defaults(action="setup")
    setup_parser.add_argument("--num-tenants",
                              default='2',
                              type=int,
                              help="Number of tenants to create on setup.")
    setup_parser.add_argument("--num-servers",
                              default='1',
                              type=int,
                              help="Number of servers per tenant to create "
                              "on setup.")
    setup_parser.add_argument("--num-volumes",
                              default='1',
                              type=int,
                              help="Number of volumes per tenant to create "
                              "on setup.")
    evacuate_parser = subparsers.add_parser("evacuate",
                                            help="Evacuate instances from "
                                                 "the given host.")
    evacuate_parser.set_defaults(action="evacuate")
    evacuate_parser.add_argument("hostname",
                                 help="The hostname of the host for "
                                      "evacuation")
    evacuate_parser = subparsers.add_parser("reassign",
                                            help="Reassign the given host "
                                                 "from one cloud to another.")
    evacuate_parser.set_defaults(action="reassign")
    evacuate_parser.add_argument("hostname",
                                 help="The hostname of the host to reassign.")
    return parser


def migrate_volumes(ctx, flow, ids):
    volume_resources = []
    volumes_flow = unordered_flow.Flow("migrate-detached-volumes")
    volumes = ctx.src_cloud.cinder.volumes.list(
        search_opts={'all_tenants': 1, 'status': 'available'})
    for volume in volumes:
        if volume.id in ids:
            resources, volume_flow = volume_tasks.migrate_volume(
                ctx, volume.id)
            flow.add(*resources)
            volumes_flow.add(volume_flow)
    flow.add(volumes_flow)
    return flow


def migrate_images(ctx, flow, ids):
    for image in ctx.src_cloud.glance.images.list():
        if image.id in ids:
            image_flow = image_tasks.migrate_image(
                ctx, image.id)
            flow.add(image_flow)
    return flow


def migrate_identity(ctx, flow, ids):
    for tenant_id in ids:
        _, identity_flow = identity_tasks.migrate_identity(
            ctx, tenant_id)
        flow.add(identity_flow)
    return flow


def migrate_resources(ctx, flow, ids):
    for tenant_id in ids:
        resources_flow = resources_tasks.migrate_resources(
            ctx, tenant_id)
        flow.add(resources_flow)
    return flow


def get_ids_by_tenant(cloud, resource_type, tenant_id):

    '''This function implements migration strategy 'tenant'

    For those types of resources that support grouping by tenant, this function
    returns a list of IDs of resources owned by the given tenant.

    :param cloud:           a collection of clients to talk to cloud services
    :param resource_type:   a type of resources designated for migration
    :param tenant_id:       an identifier of tenant that resources belong to
    :returns:               a list of IDs of resources according to passed
                            resource type
    '''

    ids = []
    if resource_type == 'users':
        ids = [user.id for user in
               cloud.keystone.users.list(tenant_id=tenant_id)]
    elif resource_type == 'images':
        ids = [image.id for image in
               cloud.glance.images.list(filters={'owner': tenant_id})]
    elif resource_type == 'servers':
        ids = [server.id for server in
               cloud.nova.servers.list(search_opts={'all_tenants': 1,
                                                    'tenant': tenant_id})]
    else:
        LOG.warn("Cannot group %s by tenant", resource_type)
    return ids


def get_ids_by_host(cloud, resource_type, hostname):

    '''Selects servers for migration based on hostname of hypervisor

    :param cloud:           a collection of clients to talk to cloud services
    :param resource_type:   a type of resources designated for migration
    :param hostname:        a name of physical servers that hosts resources
    '''

    ids = []
    if resource_type == 'servers':
        ids = [server.id for server in
               cloud.nova.servers.list(
                   search_opts={'all_tenants': 1,
                                'hypervisor_name': hostname})]
    else:
        LOG.warn("Cannot group %s by host", resource_type)
    return ids


def get_all_resource_ids(cloud, resource_type):

    '''This function implements migration strategy 'all'

    It rerurns a list of IDs of all resources of the given type in source
    cloud.

    :param cloud:            a collection of clients to talk to cloud services
    :param resource_type:    a type of resources designated for migration
    '''

    ids = []
    if resource_type == 'tenants' or resource_type == 'identity':
        ids = [tenant.id for tenant in cloud.keystone.tenants.list()]
    elif resource_type == 'roles':
        ids = [role.id for role in cloud.keystone.roles.list()]
    elif resource_type == 'users':
        ids = [user.id for user in
               cloud.keystone.users.list()]
    elif resource_type == 'images':
        ids = [image.id for image in cloud.glance.images.list()]
    elif resource_type == 'servers':
        ids = [server.id for server in
               cloud.nova.servers.list(search_opts={'all-tenants': 1})]
    elif resource_type == 'flavors':
        ids = [flavor.id for flavor in cloud.nova.flavors.list()]
    return ids


RESOURCES_MIGRATIONS = collections.OrderedDict([
    ("images", migrate_images),
    ("identity", migrate_identity),
    ("resources", migrate_resources),
    ("volumes", migrate_volumes),
])


class Events(object):
    def emit(self, event, *args, **kwargs):
        LOG.info("Event {!r}: {}, {}".format(event, args, kwargs))


def init_client(config, name, client_class, identity_class):
    identity = identity_class(config["identity"]["connection"])
    client = client_class.from_dict(name, identity, config)
    return client


def setup(plugins, events, cloud, target,
          num_tenants, num_servers, num_volumes, workloads):
    env = reset_tasks.Environment(cloud, plugins)
    runner = tasks_base.TaskflowRunner(env)
    setup_workload = runner.get_resource(reset_tasks.SetupWorkload, {
        "id": cloud.name,
        "populate": {
            "num_tenants": num_tenants,
            "num_servers": num_servers,
            "num_volumes": num_volumes,
        },
        "workloads": workloads,
    })
    runner.add(setup_workload.create)
    runner.run()


def cleanup(plugins, events, cloud, target):
    env = reset_tasks.Environment(cloud, plugins)
    runner = tasks_base.TaskflowRunner(env)
    cleanup_workload = runner.get_resource(reset_tasks.CleanupWorkload,
                                           {"id": cloud.name})
    runner.add(cleanup_workload.delete)
    runner.run()


def main():
    args = get_parser().parse_args()

    logging.basicConfig(level=logging.INFO)

    events = Events()
    Cloud, Identity = load_cloud_driver(is_fake=args.fake)
    clouds_config = args.config["CLOUDS"]
    plugins_config = args.config["PLUGINS"]
    if args.action == "migrate":
        flow = graph_flow.Flow("migrate-resources")
        store = {}
        src_config = clouds_config["source"]
        src = init_client(src_config,
                          "source",
                          Cloud,
                          Identity)
        if args.setup:
            workloads = clouds_config["source"].get("workloads", {})
            setup(plugins_config, events, src, "source",
                  args.num_tenants, args.num_servers, args.num_volumes,
                  workloads)
        dst_config = clouds_config["destination"]
        dst = init_client(dst_config,
                          "destination",
                          Cloud,
                          Identity)
        migrate_function = RESOURCES_MIGRATIONS[args.resource]
        if args.ids:
            ids = args.ids
        elif args.tenant:
            ids = get_ids_by_tenant(src, args.resource, args.tenant)
        elif args.host:
            ids = get_ids_by_host(src, args.resource, args.host)
        else:
            raise exceptions.UsageError("Missing tenant ID")
        ctx = context.Context(plugins_config, src, dst)
        resources_flow = migrate_function(ctx, flow, ids)
        if (args.dump):
            with open(args.dump, "w") as f:
                utils.dump_flow(resources_flow, f, True)
            return 0

        flows.run_flow(resources_flow, ctx.store)
    elif args.action == "cleanup":
        cloud_config = clouds_config[args.target]
        cloud = init_client(cloud_config,
                            args.target,
                            Cloud,
                            Identity)
        cleanup(plugins_config, events, cloud, args.target)
    elif args.action == "setup":
        src_config = clouds_config["source"]
        src = init_client(src_config,
                          "source",
                          Cloud,
                          Identity)
        workloads = clouds_config["source"].get("workloads", {})
        setup(plugins_config, events, src, "source",
              args.num_tenants, args.num_servers, args.num_volumes,
              workloads)
    elif args.action == "evacuate":
        src = init_client(clouds_config["source"],
                          "source",
                          Cloud,
                          Identity)
        dst = init_client(clouds_config["destination"],
                          "destination",
                          Cloud,
                          Identity)
        ctx = context.Context(plugins_config, src, dst)
        flow = evacuation_tasks.evacuate_servers(ctx, args.hostname)
        if (args.dump):
            with open(args.dump, "w") as f:
                utils.dump_flow(flow, f, True)
            return
        flows.run_flow(flow, ctx.store)
    elif args.action == "reassign":
        fuel_config = clouds_config["fuel"]["endpoint"]
        os.environ["SERVER_ADDRESS"] = fuel_config["host"]
        os.environ["LISTEN_PORT"] = str(fuel_config["port"])
        os.environ["KEYSTONE_USER"] = fuel_config["username"]
        os.environ["KEYSTONE_PASS"] = fuel_config["password"]

        src_config = clouds_config["source"]
        dst_config = clouds_config["destination"]
        config = {
            "source": src_config["environment"],
            "destination": dst_config["environment"],
        }
        src = init_client(src_config,
                          "source",
                          Cloud,
                          Identity)
        dst = init_client(dst_config,
                          "destination",
                          Cloud,
                          Identity)
        ctx = context.Context(config, src, dst)
        flow = reassignment_tasks.reassign_node(ctx, args.hostname)
        if (args.dump):
            with open(args.dump, "w") as f:
                utils.dump_flow(flow, f, True)
            return
        flows.run_flow(flow, ctx.store)

if __name__ == "__main__":
    main()
