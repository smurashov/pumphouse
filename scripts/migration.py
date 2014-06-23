import argparse
import collections
import logging
import os
import random
import time
import urllib
import yaml

import sqlalchemy as sqla

from novaclient.v1_1 import client as nova_client
from novaclient import exceptions as nova_excs

from keystoneclient.v2_0 import client as keystone_client
from keystoneclient.openstack.common.apiclient import exceptions as keystone_excs

from glanceclient import client as glance
from glanceclient import exc as glance_excs


LOG = logging.getLogger(__name__)
RO_SECURITY_GROUPS = ['default']
SERVICE_TENANT_NAME = 'services'
BUILTIN_ROLES = ('service', 'admin', '_member_')

TEST_IMAGE_URL = 'http://download.cirros-cloud.net/0.3.2/cirros-0.3.2-x86_64-disk.img'
TEST_IMAGE_FILE = '/tmp/cirros-0.3.2.img'
TEST_RESOURCE_PREFIX = "pumphouse-test"


class Error(Exception):
    pass


class NotFound(Error):
    pass


class TimeoutException(Error):
    pass


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f.read())


def get_parser():
    parser = argparse.ArgumentParser(description="Migration resources through "
                                                 "OpenStack clouds.")
    parser.add_argument("config",
                        type=safe_load_yaml,
                        help="A filename of a configuration of clouds "
                             "endpoints and a strategy.")
    subparsers = parser.add_subparsers()
    migrate_parser = subparsers.add_parser("migrate",
                                           help="Perform a migration of "
                                                "resources from a source "
                                                "cloud to a distination.")
    migrate_parser.set_defaults(action="migrate")
    migrate_parser.add_argument("resource",
                                nargs="?",
                                choices=RESOURCES_MIGRATIONS.keys(),
                                default="all",
                                help="Specify a type of resources to migrate "
                                     "to the destination cloud.")
    cleanup_parser = subparsers.add_parser("cleanup",
                                           help="Remove resources from a "
                                                "destination cloud.")
    cleanup_parser.set_defaults(action="cleanup")
    setup_parser = subparsers.add_parser("setup",
                                         help="Create resource in a source "
                                              "cloud for the test purposes.")
    setup_parser.set_defaults(action="setup")
    return parser


def read_configuration(stream):
    with stream as f:
        return yaml.safe_load(f.read())


def wait_for_delete(resource, update_resource, timeout=60,
                    check_interval=1, exceptions=(NotFound,)):
    start = time.time()
    while True:
        try:
            resource = update_resource(resource)
        except exceptions:
            break
        time.sleep(check_interval)
        if time.time() - start > timeout:
            raise TimeoutException()


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


def migrate_flavors(mapping, src, dst, id):
    for flavor in src.nova.flavors.list():
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


def migrate_images(mapping, src, dst, id):
    for image in src.glances.images.list():
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
    for n_label, n_params in addresses.iteritems():
        n1 = migrate_network(mapping, src, dst, n_label)
        for n_param in n_params:
            nics.append({
                "net-id": n1.id,
                "v4-fixed-ip": n_param["addr"],
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
    mapping[n0.id] = n1
    return n1


def migrate_servers(mapping, src, dst):
    for server in src.nova.servers.list():
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


def migrate_tenants(mapping, src, dst, id):
    for tenant in src.keystone.tenants.list():
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
        r1 = dst.nova.security_group_rules.create(
                                id,
                                ip_protocol=r0['ip_protocol'],
                                from_port=r0['from_port'],
                                to_port=r0['to_port'],
                                cidr=r0['ip_range']['cidr'])
        LOG.info("Created: %s",r1._info)
    except nova_excs.BadRequest:
        LOG.warn("Duplicated rule: %s", r0)
    except nova_excs.NotFound:
        LOG.exception("Rule create attempted for non-existent security group: %s", r0)
        raise


def migrate_secgroups(mapping, src, dst):
    for sg in src.nova.security_groups.list():
        migrate_secgroup(mapping, src, dst, sg.id)


class Identity(collections.Mapping):
    select_query = sqla.text("SELECT id, password FROM user "
                             "WHERE id = :user_id")
    update_query = sqla.text("UPDATE user SET password = :password "
                             "WHERE id = :user_id")

    def __init__(self, connection):
        self.engine = sqla.create_engine(connection)
        self.hashes = {}

    def fetch(self, user_id):
        """Fetch a hash of user's password."""
        users = self.engine.execute(self.select_query, user_id=user_id)
        for _, password in users:
            self.hashes[user_id] = password
            return password

    def push(self):
        """Push hashes of users' passwords."""
        with self.engine.begin() as conn:
            for user_id, password in self.hashes.iteritems():
                conn.execute(self.update_query,
                             user_id=user_id, password=password)

    def __len__(self):
        return len(self.hashes)

    def __iter__(self):
        return iter(self.hashes)

    def __getitem__(self, user_id):
        if user_id not in self.hashes:
            password = self.fetch(user_id)
            self.hashes[user_id] = password
        else:
            password = self.hashes[user_id]
        return password

    def update(self, iterable):
        for user_id, password in iterable:
            self.hashes[user_id] = password


class Cloud(object):
    def __init__(self, cloud_ns, user_ns, identity):
        self.cloud_ns = cloud_ns
        self.user_ns = user_ns
        self.access_ns = cloud_ns.restrict(user_ns)
        self.nova = nova_client.Client(self.access_ns.username,
                                       self.access_ns.password,
                                       self.access_ns.tenant_name,
                                       self.access_ns.auth_url,
                                       "compute")
        self.keystone = keystone_client.Client(**self.access_ns.to_dict())
        g_endpoint = self.keystone.service_catalog.get_endpoints()["image"][0]
        self.glance = glance.Client("2",
                                    endpoint=g_endpoint["publicURL"],
                                    token=self.keystone.auth_token)
        if isinstance(identity, Identity):
            self.identity = identity
        else:
            self.identity = Identity(**identity)

    def restrict(self, user_ns):
        return Cloud(self.cloud_ns, user_ns, self.identity)

    @classmethod
    def from_dict(cls, endpoint, identity):
        cloud_ns = Namespace(auth_url=endpoint["auth_url"])
        user_ns = Namespace(
            username=endpoint["username"],
            password=endpoint["password"],
            tenant_name=endpoint["tenant_name"],
        )
        return cls(cloud_ns, user_ns, identity)

    def __repr__(self):
        return "<Cloud(namespace={!r})>".format(self.access_ns)


class Namespace(object):
    __slots__ = ("username", "password", "tenant_name", "auth_url")

    def __init__(self, username=None, password=None, tenant_name=None, auth_url=None):
        self.username = username
        self.password = password
        self.tenant_name = tenant_name
        self.auth_url = auth_url

    def to_dict(self):
        return dict((attr, getattr(self, attr)) for attr in self.__slots__)

    def restrict(self, *nspace, **attrs):
        def nspace_getter(x, y, z):
            return getattr(x, y, z)

        def attrs_getter(x, y, z):
            return x.get(y, z)

        def restrict_by(attrs, getter):
            namespace = Namespace()
            for attr in self.__slots__:
                value = getter(attrs, attr, None)
                if value is None:
                    value = getattr(self, attr)
                setattr(namespace, attr, value)
            return namespace
        return restrict_by(*((nspace[0], nspace_getter)
                             if nspace else
                             (attrs, attrs_getter)))

    def __repr__(self):
        return ("<Namespace(username={!r}, password={!r}, tenant_name={!r}, "
                "auth_url={!r})>"
                .format(self.username, self.password, self.tenant_name,
                        self.auth_url))

    def __eq__(self, other):
        return (self.username == other.username and
                self.password == other.password and
                self.tenant_name == other.tenant_name and
                self.auth_url == other.auth_url)


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


def migrate_users(mapping, src, dst):
    for user in src.keystone.users.list():
        migrate_user(mapping, src, dst, user.id)


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


def migrate_roles(mapping, src, dst):
    for role in src.keystone.roles.list():
        migrate_role(mapping, src, dst, role.id)


def migrate(mapping, src, dst):
    migrate_users(mapping, src, dst)
    migrate_servers(mapping, src, dst)
    update_users_passwords(mapping, src, dst)


def cleanup(cloud):
    def is_prefixed(string):
        return string.startswith(TEST_RESOURCE_PREFIX)
    search_opts = {"all_tenants": 1}
    for server in cloud.nova.servers.list(search_opts=search_opts):
        if not is_prefixed(server.name):
            continue
        cloud.nova.servers.delete(server)
        wait_for_delete(server, cloud.nova.servers.get,
                        exceptions=(nova_excs.NotFound,))
        LOG.info("Deleted server: %s", server._info)
    for image in cloud.glance.images.list():
        if not is_prefixed(image.name):
            continue
        cloud.glance.images.delete(image.id)
        LOG.info("Deleted image: %s", dict(image))
    for secgroup in cloud.nova.security_groups.list():
        if not is_prefixed(secgroup.name):
            continue
        if secgroup.name in RO_SECURITY_GROUPS:
            for rule in secgroup.rules:
                cloud.nova.security_group_rules.delete(rule['id'])
                LOG.info("Deleted rule from default secgroup: %s", rule)
        else:
            cloud.nova.security_groups.delete(secgroup.id)
            LOG.info("Deleted secgroup: %s", secgroup._info)
    for network in cloud.nova.networks.list():
        if not is_prefixed(network.label):
            continue
        cloud.nova.networks.disassociate(network)
        cloud.nova.networks.delete(network)
        LOG.info("Deleted network: %s", network._info)
    for user in cloud.keystone.users.list():
        if is_prefixed(user.name):
            cloud.keystone.users.delete(user)
            LOG.info("Deleted user: %s", user._info)
    for role in cloud.keystone.roles.list():
        if is_prefixed(role.name):
            cloud.keystone.roles.delete(role)
            LOG.info("Deleted role: %s", role._info)
    for tenant in cloud.keystone.tenants.list():
        if is_prefixed(tenant.name):
            cloud.keystone.tenants.delete(tenant)
            LOG.info("Deleted role: %s", tenant._info)


def setup(cloud):
    prefix = TEST_RESOURCE_PREFIX
    if not os.path.isfile(TEST_IMAGE_FILE):
        LOG.info("Caching test image: %s", TEST_IMAGE_FILE)
        urllib.urlretrieve(TEST_IMAGE_URL, TEST_IMAGE_FILE)
    test_tenants = {}
    test_images = {}
    test_flavors = {}
    test_users = {}
    test_nets = {}
    test_servers = {}
    test_clouds = {}
    test_roles = {}
    for i in range(2):
        flavor = cloud.nova.flavors.create(
                    "{0}-flavor-{1}"
                   .format(prefix,
                           str(random.randint(1,0x7fffffff))),
                   '1','1','2',is_public='True')
        test_flavors[flavor.id] = flavor
        LOG.info("Created: %s", flavor._info)
        tenant = cloud.keystone.tenants.create(
                    "{0}-tenant-{1}"
                    .format(prefix,
                            str(random.randint(1, 0x7fffffff))),
                    description="pumphouse test tenant")
        test_tenants[tenant.id] = tenant
        LOG.info("Created: %s", tenant._info)
        role = cloud.keystone.roles.create(
                    "{0}-role-{1}"
                    .format(prefix,
                            str(random.randint(1, 0x7fffffff))))
        test_roles[role.id] = role
        LOG.info("Created: %s", role._info)
        user = cloud.keystone.users.create(
                    name="{0}-user-{1}"
                    .format(prefix, str(random.randint(1, 0x7fffffff))),
                    password="default",
                    tenant_id=tenant.id)
        test_users[tenant.id] = user
        LOG.info("Created: %s", user._info)
        user_role = cloud.keystone.roles.add_user_role(
                    user,
                    role,
                    tenant=tenant.id)
        LOG.info("Assigned %s: %s", user._info, role._info)
        net = cloud.nova.networks.create(
                    label="{0}-pumphouse-{1}".format(prefix, i),
                    cidr="10.10.{0}.0/24".format(i),
                    project_id=tenant.id)
        test_nets[tenant.id] = net
        LOG.info("Created: %s", net._info)
        user_ns = Namespace(username=user.name,
                            password="default",
                            tenant_name=tenant.name)
        test_clouds[tenant.id] = cloud.restrict(user_ns)
    for tenant_ref in test_tenants:
        cloud = test_clouds[tenant_ref]
        image = cloud.glance.images.create(
                    disk_format='qcow2',
                    container_format='bare',
                    name="{0}-image-{1}"
                    .format(prefix,
                            random.randint(1,0x7fffffff)))
        cloud.glance.images.upload(image.id, open(TEST_IMAGE_FILE, "rb"))
        test_images[image.id] = image
        LOG.info("Created: %s", dict(image))
        (net, _, addr) = test_nets[tenant_ref].dhcp_start.rpartition('.')
        ip = ".".join( (net, str(int(addr)+len(test_servers))) )
        nics = [{
                            "net-id": test_nets[tenant_ref].id,
                            "v4-fixed-ip": ip,
        }]
        server = cloud.nova.servers.create(
                    "{0}-{1}".format(prefix,
                                     str(random.randint(1, 0x7fffffff))),
                    image.id,
                    flavor.id,
                    nics=nics)
        test_servers[server.id] = server
        LOG.info("Created: %s", server._info)


RESOURCES_MIGRATIONS = collections.OrderedDict([
    ("all", migrate),
    ("tenants", migrate_tenants),
    ("users", migrate_users),
    ("images", migrate_images),
    ("flavors", migrate_flavors),
    ("servers", migrate_servers),
    ("security_groups", migrate_secgroups),
    ("roles", migrate_roles),
])


def main():
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.action == "migrate":
        mapping = {}
        src = Cloud.from_dict(**args.config["source"])
        dst = Cloud.from_dict(**args.config["destination"])
        migrate_resources = RESOURCES_MIGRATIONS[args.resource]
        migrate_resources(mapping, src, dst)
        LOG.info("Migration mapping: %r", mapping)
    elif args.action == "cleanup":
        dst = Cloud.from_dict(**args.config["destination"])
        cleanup(dst)
    elif args.action == "setup":
        src = Cloud.from_dict(**args.config["source"])
        setup(src)


if __name__ == "__main__":
    main()
