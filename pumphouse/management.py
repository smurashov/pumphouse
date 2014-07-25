import logging
import os
import random
import urllib

from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs
from novaclient import exceptions as nova_excs

from . import cloud as pump_cloud
from . import exceptions
from . import utils


LOG = logging.getLogger(__name__)

RO_SECURITY_GROUPS = ['default']
TEST_IMAGE_URL = ("http://download.cirros-cloud.net/0.3.2/"
                  "cirros-0.3.2-x86_64-disk.img")
TEST_IMAGE_FILE = '/tmp/cirros-0.3.2.img'
TEST_RESOURCE_PREFIX = "pumphouse-test"
FLOATING_IP_STRING = "172.16.0.{}"


def become_admin_in_tenant(cloud, user, tenant):
    """Adds the user into the tenant with an admin role.

    :param cloud: the instance of :class:`pumphouse.cloud.Cloud`
    :param user: the user's unique identifier
    :param tenant: an unique identifier of the tenant
    :raises: exceptions.NotFound
    """
    admin_roles = [r
                   for r in cloud.keystone.roles.list()
                   if r.name == "admin"]
    if not admin_roles:
        raise exceptions.NotFound()
    admin_role = admin_roles[0]
    try:
        cloud.keystone.tenants.add_user(tenant, user, admin_role)
    except keystone_excs.Conflict:
        LOG.warning("User %r already in %r tenant with 'admin' role",
                    user, tenant)


def cleanup(events, cloud, target):
    def is_prefixed(string):
        return string.startswith(TEST_RESOURCE_PREFIX)
    search_opts = {"all_tenants": 1}
    for server in cloud.nova.servers.list(search_opts=search_opts):
        if not is_prefixed(server.name):
            continue
        cloud.nova.servers.delete(server)
        utils.wait_for(server, cloud.nova.servers.get,
                       expect_excs=(nova_excs.NotFound,))
        LOG.info("Deleted server: %s", server._info)
        hostname = getattr(server, "OS-EXT-SRV-ATTR:hypervisor_hostname")
        events.emit("server delete", {
            "cloud": target,
            "id": server.id,
            "host_name": hostname,
        }, namespace="/events")
    for flavor in cloud.nova.flavors.list():
        if is_prefixed(flavor.name):
            cloud.nova.flavors.delete(flavor)
            LOG.info("Deleted flavor: %s", flavor._info)
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
    for floating_ip in cloud.nova.floating_ips_bulk.list():
        cloud.nova.floating_ips_bulk.delete(floating_ip.address)
        LOG.info("Deleted floating ip: %s", floating_ip._info)
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
            events.emit("tenant delete", {
                "cloud": target,
                "id": tenant.id,
            }, namespace="/events")
    services = cloud.nova.services.list(binary="nova-compute")
    for service in services:
        if service.status == "disabled":
            cloud.nova.services.enable(service.host, "nova-compute")
            LOG.info("Enabled the nova-compute service on %s", service.host)
            events.emit("", {
                "cloud": target,
                "name": service.host,
            }, namespace="/events")


def setup(events, cloud, target, num_tenants, num_servers):

    """Prepares test resources in the source cloud

    :param cloud:       an instance of Cloud, collection of clients to
                        OpenStack services.
    :param num_tenants: a number of tenants to create in the source cloud.
    :type num_tenants:  int
    :param num_servers: a number of servers to create per tenant
    :type servers:      int
    """

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
    test_tenant_clouds = {}
    test_roles = {}
    for i in range(num_tenants):
        flavor = cloud.nova.flavors.create(
            "{0}-flavor-{1}"
            .format(prefix,
                    str(random.randint(1, 0x7fffffff))),
            '1024', '1', '5', is_public='True')
        test_flavors[flavor.id] = flavor
        LOG.info("Created: %s", flavor._info)
        tenant_id = str(random.randint(1, 0x7fffffff))
        tenant = cloud.keystone.tenants.create(
            "{0}-tenant-{1}"
            .format(prefix, tenant_id),
            description="pumphouse test tenant {0}".format(tenant_id))
        become_admin_in_tenant(cloud, cloud.keystone.auth_ref.user_id, tenant)
        tenant_ns = cloud.user_ns.restrict(tenant_name=tenant.name)
        tenant_cloud = cloud.restrict(tenant_ns)
        test_tenant_clouds[tenant.id] = tenant_cloud
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
            user.id,
            role.id,
            tenant=tenant.id)
        LOG.info("Assigned: %s", user_role)
        try:
            net = tenant_cloud.nova.networks.create(
                label="{0}-pumphouse-{1}".format(prefix, i),
                cidr="10.10.{}.0/24".format(i),
                project_id=tenant.id)
        except nova_excs.Conflict:
            try:
                net = tenant_cloud.nova.networks.find(
                    project_id=tenant.id)
            except nova_excs.NotFound:
                LOG.exception("Not found at lest one network for tenant %s",
                              tenant.id)
                raise
            else:
                LOG.info("Already exists: %s", net._info)
                test_nets[tenant.id] = net
        else:
            LOG.info("Created: %s", net._info)
            test_nets[tenant.id] = net
        user_ns = pump_cloud.Namespace(username=user.name,
                                       password="default",
                                       tenant_name=tenant.name)
        test_clouds[tenant.id] = cloud.restrict(user_ns)
        events.emit("tenant create", {
            "cloud": target,
            "id": tenant.id,
            "name": tenant.name,
            "description": tenant.description,
        }, namespace="/events")
    for tenant_ref in test_tenants:
        user_cloud = test_clouds[tenant_ref]
        tenant_cloud = test_tenant_clouds[tenant_ref]
        image = user_cloud.glance.images.create(
            disk_format='qcow2',
            container_format='bare',
            name="{0}-image-{1}"
            .format(prefix,
                    random.randint(1, 0x7fffffff)))
        user_cloud.glance.images.upload(image.id, open(TEST_IMAGE_FILE, "rb"))
        test_images[image.id] = image
        LOG.info("Created: %s", dict(image))
        for i in range(num_servers):
            (net, _, addr) = test_nets[tenant_ref].dhcp_start.rpartition('.')
            ip = ".".join((net, str(int(addr) + len(test_servers))))
            nics = [{
                "net-id": test_nets[tenant_ref].id,
                "v4-fixed-ip": ip,
            }]
            server = user_cloud.nova.servers.create(
                "{0}-{1}".format(prefix,
                                 str(random.randint(1, 0x7fffffff))),
                image.id,
                flavor.id,
                nics=nics)
            test_servers[server.id] = server
            server = utils.wait_for(server.id, cloud.nova.servers.get,
                                    value="ACTIVE")
            LOG.info("Created server: %s", server._info)
            hostname = getattr(server, "OS-EXT-SRV-ATTR:hypervisor_hostname")
            events.emit("server boot", {
                "cloud": target,
                "id": server.id,
                "name": server.name,
                "tenant_id": server.tenant_id,
                "image_id": server.image["id"],
                "host_name": hostname,
                "status": server.status.lower(),
            }, namespace="/events")
            try:
                pool = "{}-pool-{}".format(prefix, tenant_ref)
                floating_addr = FLOATING_IP_STRING.format(136 + len(
                    test_servers))
                floating_range = tenant_cloud.nova.floating_ips_bulk.create(
                    floating_addr,
                    pool=pool)
                floating_ip = user_cloud.nova.floating_ips.create(
                    pool=pool)
            except Exception as exc:
                LOG.exception("Cannot create floating ip: %s",
                              exc.message)
                pass
            else:
                LOG.info("Created: %s", floating_ip._info)
                try:
                    server.add_floating_ip(floating_ip.ip, ip)
                except nova_excs.NotFound:
                    LOG.exception("Floating IP not found: %s",
                                  floating_ip._info)
                    raise
                else:
                    server = cloud.nova.servers.get(server)
                    LOG.info("Assigned floating ip %s to server: %s",
                             floating_ip._info,
                             server._info)
