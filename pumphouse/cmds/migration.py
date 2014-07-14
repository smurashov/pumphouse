import argparse
import collections
import logging
import time

from pumphouse import management
from pumphouse import exceptions
from pumphouse import utils

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


def migrate_flavor(mapping, src, dst, id):
    f0 = src.nova.flavors.get(id)
    if f0.id in mapping:
        LOG.warn("Skipped because mapping: %s", f0._info)
        return dst.nova.flavors.get(mapping[f0.id])
    try:
        f1 = dst.nova.flavors.get(f0)
    except nova_excs.NotFound:
        f1 = dst.nova.flavors.create(f0.name, f0.ram, f0.vcpus, f0.disk,
                                     flavorid=f0.id,
                                     ephemeral=f0.ephemeral,
                                     swap=f0.swap or 0,
                                     rxtx_factor=f0.rxtx_factor,
                                     is_public=f0.is_public)
        LOG.info("Created: %s", f1._info)
    else:
        LOG.warn("Already exists: %s", f1._info)
        mapping[f0.id] = f1.id
    return f1


def migrate_flavors(mapping, src, dst, ids):
    for flavor in src.nova.flavors.list():
        if flavor.id in ids:
            migrate_flavor(mapping, src, dst, flavor)


def migrate_image(mapping, src, dst, id):
    def upload(src_image, dst_image):
        data = src.glance.images.data(src_image.id)
        dst.glance.images.upload(dst_image.id, data._resp)
        LOG.info("Uploaded image: %s -> %s", src_image, dst_image)

    def create(image, **kwargs):
        new = dst.glance.images.create(disk_format=image.disk_format,
                                       container_format=image.container_format,
                                       visibility=image.visibility,
                                       min_ram=image.min_ram,
                                       min_disk=image.min_disk,
                                       name=image.name,
                                       protected=image.protected,
                                       **kwargs)
        LOG.info("Create image: %s", new)
        return new
    i0 = src.glance.images.get(id)
    if i0.id in mapping:
        LOG.warn("Skipped because mapping: %s", dict(i0))
        return dst.glance.images.get(mapping[i0.id])
    imgs1 = dict([(i.checksum, i)
                  for i in dst.glance.images.list()
                  if hasattr(i, "checksum")])
    if not hasattr(i0, "checksum"):
        LOG.exception("Image has no checksum: %s", i0.id)
        raise
    elif i0.checksum not in imgs1:
        params = {}
        if hasattr(i0, "kernel_id"):
            LOG.info("Found kernel image: %s", i0.kernel_id)
            ik1 = migrate_image(mapping, src, dst, i0.kernel_id)
            params["kernel_id"] = ik1["id"]
        if "ramdisk_id" in i0:
            LOG.info("Found ramdisk image: %s", i0.ramdisk_id)
            ir0 = migrate_image(mapping, src, dst, i0.ramdisk_id)
            params["ramdisk_id"] = ir0["id"]
        i1 = create(i0, **params)
        upload(i0, i1)
    else:
        i1 = imgs1.get(i0.checksum)
        LOG.info("Already present: %s", i1)
    mapping[i0.id] = i1.id
    return i1


def migrate_images(mapping, src, dst, ids):
    for image in src.glance.images.list():
        if image.id in ids:
            migrate_image(mapping, src, dst, image.id)


def migrate_server(mapping, src, dst, id):
    s0 = src.nova.servers.get(id)
    svrs1 = dst.nova.servers.list()
    if s0.id in mapping:
        LOG.warn("Skipped because mapping: %s", s0._info)
        return dst.nova.servers.get(mapping[s0.id])
    f1 = migrate_flavor(mapping, src, dst, s0.flavor["id"])
    for secgroup in s0.security_groups:
        sg0 = src.nova.security_groups.find(name=secgroup['name'])
        sg1 = migrate_secgroup(mapping, src, dst, sg0.id)
        # TODO(akscram): Security groups migrated but never assigned
        #                for a new server.
    nics = []
    i1 = migrate_image(mapping, src, dst, s0.image["id"])
    addresses = s0.addresses
    floating_ips = dict()
    for n_label, n_params in addresses.iteritems():
        n1 = migrate_network(mapping, src, dst, n_label)
        fixed_ip = n_params[0]
        floating_ips[fixed_ip["addr"]] = n_params[1:]
        nics.append({
            "net-id": n1.id,
            "v4-fixed-ip": fixed_ip["addr"],
        })
    try:
        src.nova.servers.suspend(s0)
        LOG.info("Suspended: %s", s0._info)
        try:
            s1 = dst.nova.servers.create(s0.name, i1, f1, nics=nics)
        except:
            LOG.exception("Failed to create server: %s", s0._info)
            raise
        else:
            src.nova.servers.delete(s0)
            LOG.info("Deleted: %s", s0)
    except:
        LOG.exception("Error occured in migration: %s", s0._info)
        src.nova.servers.resume(s0)
        raise
    mapping[s0.id] = s1.id
    LOG.info("Created: %s", s1._info)
    for fixed_ip in floating_ips:
        for floating_ip_dict in floating_ips[fixed_ip]:
            floating_ip1 = migrate_floating_ip(mapping,
                                               src,
                                               dst,
                                               floating_ip_dict["addr"])
            while True:
                try:
                    s1.add_floating_ip(floating_ip1.address,
                                       fixed_ip)
                except nova_excs.BadRequest:
                    LOG.warn("Network info not ready for instance: %s",
                             s1._info)
                    time.sleep(1)
                    continue
                else:
                    break
            s1 = dst.nova.servers.get(s1)
            LOG.info("Assigned floating ip %s to server: %s",
                     floating_ip1.address,
                     s1._info)
    return s1


def migrate_network(mapping, src, dst, name):
    nets0 = dict((n.label, n) for n in src.nova.networks.list())
    nets1 = dict((n.label, n) for n in dst.nova.networks.list())
    n0 = nets0[name]
    if n0.id in mapping:
        LOG.warn("Skipped because mapping: %s", n0._info)
        return dst.nova.networks.get(mapping[n0.id])
    n1 = dst.nova.networks.create(label=n0.label,
                                  cidr=n0.cidr,
                                  cidr_v6=n0.cidr_v6,
                                  dns1=n0.dns1,
                                  dns2=n0.dns2,
                                  gateway=n0.gateway,
                                  gateway_v6=n0.gateway_v6,
                                  multi_host=n0.multi_host,
                                  priority=n0.priority,
                                  project_id=n0.project_id,
                                  vlan_start=n0.vlan,
                                  vpn_start=n0.vpn_private_address)
    mapping[n0.id] = n1.id
    return n1


def migrate_servers(mapping, src, dst, ids):
    search_opts = {"all_tenants": 1}
    for server in src.nova.servers.list(search_opts=search_opts):
        if server.id in ids:
            migrate_server(mapping, src, dst, server.id)


# TODO(akscram): We should to check that it's worked.
def migrate_tenant(mapping, src, dst, id):
    t0 = src.keystone.tenants.get(id)
    if t0.id in mapping:
        LOG.warn("Skipped because mapping: %s", t0._info)
        return dst.keystone.tenants.get(mapping[t0.id])
    if t0.name == SERVICE_TENANT_NAME:
        LOG.exception("Will NOT migrate service tenant: %s",
                      t0._info)
        raise
    try:
        t1 = dst.keystone.tenants.find(name=t0.name)
    except keystone_excs.NotFound:
        t1 = dst.keystone.tenants.create(t0.name,
                                         description=t0.description,
                                         enabled=t0.enabled)
        LOG.info("Created: %s", t1._info)
    else:
        LOG.warn("Already exists: %s", t1._info)
    return t1


def migrate_tenants(mapping, src, dst, ids):
    for tenant in src.keystone.tenants.list():
        if tenant.id in ids:
            migrate_tenant(mapping, src, dst, tenant)


def migrate_secgroup(mapping, src, dst, id):
    sg0 = src.nova.security_groups.get(id)
    t0 = src.keystone.tenants.find(id=sg0.tenant_id)
    t1 = migrate_tenant(mapping, src, dst, t0.id)
    try:
        sg1 = dst.nova.security_groups.find(name=sg0.name)
    except nova_excs.NotFound:
        sg1 = dst.nova.security_groups.create(sg0.name,
                                              sg0.description)
        LOG.info("Created: %s", sg1._info)
    else:
        LOG.warn("Already exists: %s", sg1._info)
    for rule in sg0.rules:
        migrate_secgroup_rule(mapping, src, dst, rule, sg1.id)
    return sg1


def migrate_secgroup_rule(mapping, src, dst, src_rule, id):
    r0 = src_rule
    try:
        r1 = dst.nova.security_group_rules.create(id,
                                                  ip_protocol=r0[
                                                      'ip_protocol'],
                                                  from_port=r0[
                                                      'from_port'],
                                                  to_port=r0['to_port'],
                                                  cidr=r0[
                                                      'ip_range']['cidr'])
        LOG.info("Created: %s", r1._info)
    except nova_excs.BadRequest:
        LOG.warn("Duplicated rule: %s", r0)
    except nova_excs.NotFound:
        LOG.exception("Rule create attempted for non-existent "
                      "security group: %s", r0)
        raise


def migrate_secgroups(mapping, src, dst, ids):
    for sg in src.nova.security_groups.list():
        if sg.id in ids:
            migrate_secgroup(mapping, src, dst, sg.id)


def migrate_user(mapping, src, dst, id):
    u0 = src.keystone.users.get(id)
    user_dict = dict(name=u0.name,
                     password='default',
                     enabled=u0.enabled)
    if hasattr(u0, "tenantId"):
        t0 = src.keystone.tenants.get(u0.tenantId)
        if t0.name == SERVICE_TENANT_NAME:
            LOG.exception("Will NOT migrate service user: %s",
                          u0._info)
            return
        t1 = migrate_tenant(mapping, src, dst, t0.id)
        user_dict['tenant_id'] = t1.id
    if hasattr(u0, "email"):
        user_dict['email'] = u0.email
    try:
        LOG.debug("Looking up user in dst by username: %s", u0.username)
        u1 = dst.keystone.users.find(name=u0.name)
    except keystone_excs.NotFound:
        src.identity.fetch(u0.id)
        u1 = dst.keystone.users.create(**user_dict)
        LOG.info("Created: %s", u1._info)
        LOG.warn("Password for %s doesn't match the original user!", u1.name)
        # TODO(ogelbukh): Add password synchronization logic here
    else:
        LOG.warn("Already exists: %s", u1._info)
    mapping[u0.id] = u1.id
    for tenant in src.keystone.tenants.list():
        t1 = migrate_tenant(mapping, src, dst, tenant.id)
        user_roles = src.keystone.roles.roles_for_user(u0.id, tenant=tenant.id)
        for user_role in user_roles:
            r1 = migrate_role(mapping, src, dst, user_role.id)
            try:
                dst.keystone.roles.add_user_role(u1.id, r1.id, t1)
            except keystone_excs.Conflict:
                LOG.warn("Role %s already assigned to user %s in tenant %s",
                         u1.name,
                         r1.name,
                         tenant.name)
            else:
                LOG.info("Created role %s assignment for user %s in tenant %s",
                         u1.name,
                         r1.name,
                         tenant.name)
    return u1


def update_users_passwords(mapping, src, dst):
    def with_mapping(identity):
        for user_id, password in identity.iteritems():
            yield mapping[user_id], password

    dst.identity.update(with_mapping(src.identity))
    dst.identity.push()


def migrate_users(mapping, src, dst, ids):
    for user in src.keystone.users.list():
        if user.id in ids:
            migrate_user(mapping, src, dst, user.id)
    LOG.info("Migration mapping: %r", mapping)


def migrate_role(mapping, src, dst, id):
    r0 = src.keystone.roles.get(id)
    if r0.id in mapping:
        LOG.warn("Skipped because mapping: %s", r0._info)
        return dst.keystone.roles.get(mapping[r0.id])
    try:
        r1 = dst.keystone.roles.find(name=r0.name)
    except keystone_excs.NotFound:
        if r0.name not in BUILTIN_ROLES:
            r1 = dst.keystone.roles.create(r0.name)
            LOG.info("Created: %s", r1._info)
        else:
            LOG.warn("Will NOT migrate special role: %s", r0.name)
    else:
        LOG.warn("Already exists: %s", r1._info)
    mapping[r0.id] = r1.id
    return r1


def migrate_roles(mapping, src, dst, ids):
    for role in src.keystone.roles.list():
        if role.id in ids:
            migrate_role(mapping, src, dst, role.id)


def migrate_floating_ip(mapping, src, dst, ip):

    '''Create IP address in floating IP address pool in destination cloud

    Creates IP address if it does not exist. Creates a pool in destination
    cloud as well if it does not exist.

    :param mapping:     dict mapping entity ids in source and target clouds
    :param src:         Cloud object representing source cloud
    :param dst:         Cloud object representing destination cloud
    :param ip:          IP address
    :type ip:           string
    '''

    floating_ip0 = src.nova.floating_ips_bulk.find(address=ip)
    ip_pool0 = src.nova.floating_ip_pools.find(name=floating_ip0.pool)
    try:
        floating_ip1 = dst.nova.floating_ips_bulk.find(address=ip)
    except nova_excs.NotFound:
        dst.nova.floating_ips_bulk.create(floating_ip0.address,
                                          pool=ip_pool0.name)
        try:
            floating_ip1 = dst.nova.floating_ips_bulk.find(address=ip)
        except nova_excs.NotFound:
            LOG.exception("Not added: %s", ip)
            raise exceptions.Error()
        else:
            LOG.info("Created: %s", floating_ip1._info)
    else:
        LOG.warn("Already exists, %s", floating_ip1._info)
    return floating_ip1


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


def main():
    args = get_parser().parse_args()

    logging.basicConfig(level=logging.INFO)

    Cloud = load_cloud_driver(is_fake=args.fake)
    if args.action == "migrate":
        mapping = {}
        src = Cloud.from_dict(**args.config["source"])
        if args.setup:
            management.setup(src, args.num_tenants, args.num_servers)
        dst = Cloud.from_dict(**args.config["destination"])
        migrate_resources = RESOURCES_MIGRATIONS[args.resource]
        if args.ids:
            ids = args.ids
        elif args.tenant:
            ids = get_ids_by_tenant(src, args.resource, args.tenant)
        elif args.host:
            ids = get_ids_by_host(src, args.resource, args.host)
        else:
            ids = get_all_resource_ids(src, args.resource)
        migrate_resources(mapping, src, dst, ids)
        LOG.info("Migration mapping: %r", mapping)
    elif args.action == "cleanup":
        cloud = Cloud.from_dict(**args.config[args.target])
        management.cleanup(cloud)
    elif args.action == "setup":
        src = Cloud.from_dict(**args.config["source"])
        management.setup(src, args.num_tenants, args.num_servers)
    elif args.action == "evacuate":
        cloud = Cloud.from_dict(**args.config["source"])
        evacuate(cloud, args.host)


if __name__ == "__main__":
    main()
