import argparse
import collections
import logging
import time
import yaml

from novaclient.v1_1 import client as nova_client
from novaclient import exceptions as nova_excs

from keystoneclient.v2_0 import client as keystone_client
from keystoneclient.openstack.common.apiclient import exceptions as keystone_excs

from glanceclient import client as glance
from glanceclient import exc as glance_excs


LOG = logging.getLogger(__name__)
RO_SECURITY_GROUPS = ['default']
SERVICE_TENANT_NAME = 'services'


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
    parser.add_argument("action",
                        choices=("migrate", "cleanup"),
                        help="Perform a migration of resources from a source "
                             "cloud to a distination.")
    parser.add_argument("resource",
                        nargs="?",
                        choices=RESOURCES_MIGRATIONS.keys(),
                        default="all",
                        help="Specify a type of resources to migrate to the "
                        "destination cloud")
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
    t1 = migrate_tenant(src, dst, t0.id)
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


class Cloud(object):
    def __init__(self, endpoint):
        self.nova = nova_client.Client(endpoint["username"],
                                       endpoint["password"],
                                       endpoint["tenant_name"],
                                       endpoint["auth_url"],
                                       "compute")
        self.keystone = keystone_client.Client(**endpoint)
        g_endpoint = self.keystone.service_catalog.get_endpoints()["image"][0]
        self.glance = glance.Client("2",
                                    endpoint=g_endpoint["publicURL"],
                                    token=self.keystone.auth_token)

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
            raise
        t1 = migrate_tenant(src, dst, t0.id)
        user_dict['tenant_id'] = t1.id
    if hasattr(u0, "email"):
        user_dict['email'] = u0.email
    try:
        LOG.debug("Looking up user in dst by username: %s", u0.username)
        u1 = dst.keystone.users.find(name=u0.name)
    except keystone_excs.NotFound:
        u1 = dst.keystone.users.create(**user_dict)
        LOG.info("Created: %s", u1._info)
        LOG.warn("Password for %s doesn't match the original user!", u1.name)
        # TODO(ogelbukh): Add password synchronization logic here
    else:
        LOG.warn("Already exists: %s", u1._info)
    mapping[u0.id] = u1.id
    return u1


def migrate_users(src, dst):
    mapping = {}
    for user in src.keystone.users.list():
        migrate_user(mapping, src, dst, user.id)
    LOG.info("Migration mapping: %r", mapping)


def migrate(src, dst):
    mapping = {}
    migrate_servers(mapping, src, dst)
    LOG.info("Migration mapping: %r", mapping)


def cleanup(cloud):
    for server in cloud.nova.servers.list():
        cloud.nova.servers.delete(server)
        wait_for_delete(server, cloud.nova.servers.get,
                        exceptions=(nova_excs.NotFound,))
        LOG.info("Deleted server: %s", server._info)
    for image in cloud.glance.images.list():
        cloud.glance.images.delete(image.id)
        LOG.info("Deleted image: %s", dict(image))
    for secgroup in cloud.nova.security_groups.list():
        if secgroup.name in RO_SECURITY_GROUPS:
            for rule in secgroup.rules:
                cloud.nova.security_group_rules.delete(rule['id'])
                LOG.info("Deleted rule from default secgroup: %s", rule)
        else:
            cloud.nova.security_groups.delete(secgroup.id)
            LOG.info("Deleted secgroup: %s", secgroup._info)
    for network in cloud.nova.networks.list():
        cloud.nova.networks.delete(network)
        LOG.info("Deleted network: %s", network._info)


RESOURCES_MIGRATIONS = collections.OrderedDict([
    ("all", migrate),
    ("tenants", migrate_tenants),
    ("users", migrate_users),
    ("images", migrate_images),
    ("servers", migrate_servers),
    ("security_groups", migrate_secgroups),
])


def main():
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    dst = Cloud(args.config["destination"]["endpoint"])
    if args.action == "migrate":
        src = Cloud(args.config["source"]["endpoint"])
        migrate_resources = RESOURCES_MIGRATIONS[args.resource]
        migrate_resources(src, dst)
    elif args.action == "cleanup":
        cleanup(dst)


if __name__ == "__main__":
    main()
