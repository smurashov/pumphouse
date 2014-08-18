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
import time

from pumphouse import management
from pumphouse import exceptions
from pumphouse import utils
from pumphouse import tasks
from pumphouse import flows

from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs
from novaclient import exceptions as nova_excs


LOG = logging.getLogger(__name__)

SERVICE_TENANT_NAME = 'services'
BUILTIN_ROLES = ('service', 'admin', '_member_')


def load_cloud_driver(is_fake=False):
    if is_fake:
        import_path = "pumphouse.fake.Cloud"
    else:
        import_path = "pumphouse.cloud.Cloud"
    cloud_driver = utils.load_class(import_path)
    return cloud_driver


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
    migrate_parser.add_argument("resource",
                                choices=RESOURCES_MIGRATIONS.keys(),
                                nargs="?",
                                default="servers",
                                help="Specify a type of resources to migrate "
                                     "to the destination cloud.")
    migrate_filter = migrate_parser.add_mutually_exclusive_group(
        required=False)
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
    evacuate_parser = subparsers.add_parser("evacuate",
                                            help="Evacuate instances from "
                                                 "the given host.")
    evacuate_parser.set_defaults(action="evacuate")
    evacuate_parser.add_argument("host",
                                 help="The source host of the evacuation")
    return parser


def migrate_flavors(src, dst, flow, store, ids):
    for flavor in src.nova.flavors.list():
        if flavor.id in ids:
            flow.add(tasks.migrate_flavor(mapping, src, dst, flavor.id))
    return flow, store


def migrate_images(src, dst, flow, store, ids):
    for image in src.glance.images.list():
        if image.id in ids:
            flow.add(tasks.migrate_image(mapping, src, dst, image.id))
    return flow, store


def migrate_servers(src, dst, flow, store, ids):
    search_opts = {"all_tenants": 1}
    for server in src.nova.servers.list(search_opts=search_opts):
        if server.id in ids:
            flow.add(tasks.migrate_server(mapping, src, dst, server.id))
    return flow, store


def migrate_tenants(src, dst, flow, store, ids):
    for tenant in src.keystone.tenants.list():
        if tenant.id in ids:
            flow.add(tasks.tenant.migrate_tenant(src, dst, store, tenant.id))
    return flow, store


def migrate_secgroups(src, dst, flow, store, ids):
    for sg in src.nova.security_groups.list():
        if sg.id in ids:
            flow.add(tasks.migrate_secgroup(mapping, src, dst, sg.id))
    return flow, store


def migrate_users(src, dst, store, ids):
    for user in src.keystone.users.list():
        if user.id in ids:
           flow.add(tasks.migrate_user(mapping, src, dst, user.id))
    return flow, store


def migrate_roles(src, dst, flow, store, ids):
    for role in src.keystone.roles.list():
        if role.id in ids:
            flow.add(tasks.migrate_role(mapping, src, dst, role.id))
    return flow, store


def migrate(mapping, src, dst):
    migrate_users(mapping, src, dst)
    migrate_servers(mapping, src, dst)
    update_users_passwords(mapping, src, dst)


def evacuate(cloud, host):
    binary = "nova-compute"
    try:
        hypervs = cloud.nova.hypervisors.search(host, servers=True)
    except nova_excs.NotFound:
        LOG.exception("Could not find hypervisors at the host %r.", host)
    else:
        if len(hypervs) > 1:
            LOG.warning("More than one hypervisor found at the host: %s",
                        host)
        for hyperv in hypervs:
            details = cloud.nova.hypervisors.get(hyperv.id)
            host = details.service["host"]
            cloud.nova.services.disable(host, binary)
            try:
                for server in hyperv.servers:
                    cloud.nova.servers.live_migrate(server["uuid"], None,
                                                    True, False)
            except Exception:
                LOG.exception("An error occured during evacuation servers "
                              "from the host %r", host)
                cloud.nova.services.enable(host, binary)


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
    if resource_type == 'tenants':
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
    elif resource_type == 'security_groups':
        ids = [secgroup.id for secgroup in cloud.nova.security_groups.list()]
    return ids


RESOURCES_MIGRATIONS = collections.OrderedDict([
    ("tenants", migrate_tenants),
    ("users", migrate_users),
    ("images", migrate_images),
    ("flavors", migrate_flavors),
    ("servers", migrate_servers),
    ("security_groups", migrate_secgroups),
    ("roles", migrate_roles),
])


class Events(object):
    def emit(self, *args, **kwargs):
        pass


def main():
    args = get_parser().parse_args()

    logging.basicConfig(level=logging.INFO)

    events = Events()
    flow = unordered_flow.Flow("migrate-resources")
    Cloud = load_cloud_driver(is_fake=args.fake)
    if args.action == "migrate":
        store = {}
        src_config = args.config["source"]
        src = Cloud.from_dict(src_config.get("endpoint"),
                              src_config.get("identity"))
        if args.setup:
            workloads = args.config["source"].get("workloads", {})
            management.setup(events, src, "source", args.num_tenants,
                             args.num_servers, workloads)
        dst_config = args.config["destination"]
        dst = Cloud.from_dict(dst_config.get("endpoint"),
                              dst_config.get("identity"))
        migrate_resources = RESOURCES_MIGRATIONS[args.resource]
        if args.ids:
            ids = args.ids
        elif args.tenant:
            ids = get_ids_by_tenant(src, args.resource, args.tenant)
        elif args.host:
            ids = get_ids_by_host(src, args.resource, args.host)
        else:
            ids = get_all_resource_ids(src, args.resource)
        flows.run_flow(migrate_resources(src, dst, flow, store, ids))
    elif args.action == "cleanup":
        cloud_config = args.config[args.target]
        cloud = Cloud.from_dict(cloud_config.get("endpoint"),
                                cloud_config.get("identity"))
        management.cleanup(events, cloud, args.target)
    elif args.action == "setup":
        src_config = args.config["source"]
        src = Cloud.from_dict(src_config.get("endpoint"),
                              src_config.get("identity"))
        workloads = args.config["source"].get("workloads", {})
        management.setup(events, src, "source", args.num_tenants,
                         args.num_servers, workloads)
    elif args.action == "evacuate":
        cloud_config = args.config["source"]
        cloud = Cloud.from_dict(cloud_config.get("endpoint"),
                                cloud_config.get("identity"))
        evacuate(cloud, args.host)

if __name__ == "__main__":
    main()
