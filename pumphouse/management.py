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

import logging
import os
import random
import urllib

from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs
from novaclient import exceptions as nova_excs

from pumphouse import exceptions
from pumphouse import utils

LOG = logging.getLogger(__name__)

RO_SECURITY_GROUPS = ['default']
TEST_IMAGE_URL = ("http://download.cirros-cloud.net/0.3.2/"
                  "cirros-0.3.2-x86_64-disk.img")
TEST_IMAGE_FILE = '/tmp/cirros-0.3.2.img'
TEST_RESOURCE_PREFIX = "pumphouse-test"
FLOATING_IP_STRING = "172.16.0.{}"
# TODO(ogelbukh): make FLATDHCP actual configuration parameter and/or
# command-line parameter, maybe autodetected in future
FLATDHCP = True


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
        try:
            server_floating_ips = cloud.nova.floating_ips_bulk.findall(
                instance_uuid=server.id)
        except nova_excs.NotFound:
            LOG.info("No floating ips found for server: %s",
                     server._info)
        else:
            for floating_ip in server_floating_ips:
                cloud.nova.servers.remove_floating_ip(server,
                                                      floating_ip.address)
                LOG.info("Removed floating ip address: %s",
                         floating_ip._info)
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


def generate_flavors_list(num):
    yield {"name": "{}-flavor"
           .format(TEST_RESOURCE_PREFIX),
           "ram": 1024,
           "vcpu": 1,
           "disk": 5}


def generate_tenants_list(num):
    for i in xrange(num):
        tenant_ref = str(random.randint(1, 0x7fffffff))
        yield {"name": "{}-{}".format(TEST_RESOURCE_PREFIX, tenant_ref),
               "description": "pumphouse test tenant {}".format(tenant_ref),
               "username": "{}-user-{}"
                           .format(TEST_RESOURCE_PREFIX, tenant_ref)}


def generate_floating_ips_list(num):
    pool = "{}-pool".format(TEST_RESOURCE_PREFIX)
    addr_list = [FLOATING_IP_STRING.format(136 + i) for i in xrange(num)]
    yield {pool: addr_list}


def generate_images_list(num):
    yield {"name": "{}-image".format(TEST_RESOURCE_PREFIX),
           "disk_format": "qcow2",
           "container_format": "bare",
           "visibility": "public",
           "url": TEST_IMAGE_URL}


def generate_servers_list(num, images, flavors):
    for i in xrange(num):
        server_ref = str(random.randint(1, 0x7fffffff))
        image = random.choice(images)
        flavor = random.choice(flavors)
        yield {"name": "{}-{}".format(TEST_RESOURCE_PREFIX, server_ref),
               "image": image,
               "flavor": flavor}


def setup_floating_ip(cloud, floating_ip):
    try:
        ip_range = cloud.nova.floating_ips_bulk.create(
            floating_ip["addr"], pool=floating_ip["pool"])
    except Exception as exc:
        LOG.exception("Cannot create floating ip: %s",
                      exc.message)
        raise
    else:
        return ip_range


def setup_secgroup(cloud, name='default'):
    secgroup = cloud.nova.security_groups.find(name=name)
    cloud.nova.security_group_rules.create(
        secgroup.id,
        ip_protocol='ICMP',
        from_port='-1',
        to_port='-1',
        cidr='0.0.0.0/0')
    cloud.nova.security_group_rules.create(
        secgroup.id,
        ip_protocol='TCP',
        from_port='80',
        to_port='80',
        cidr='0.0.0.0/0')
    return secgroup


def setup_image(cloud, image_dict):
    url = image_dict.pop("url")
    image_dict["visibility"] = image_dict.get("visibility", "public")
    image = cloud.glance.images.create(**image_dict)
    if not cloud.__module__ == "pumphouse.fake":
        image_file = cache_image_file(url)
        cloud.glance.images.upload(image.id,
                                   open(image_file.name, "rb"))
    return image


def cache_image_file(url=TEST_IMAGE_URL):
    tmpfile = os.tmpfile()
    LOG.info("Caching test image: %s", tmpfile.name)
    urllib.urlretrieve(url, tmpfile.name)
    return tmpfile


def setup_server(cloud, server_dict):
    image = list(cloud.glance.images.list(
        filters={
            "name": server_dict["image"]["name"]
        }))[0]
    flavor = cloud.nova.flavors.find(name=server_dict["flavor"]["name"])
    server_params = (server_dict["name"],
                     image.id,
                     flavor.id)
    server = cloud.nova.servers.create(*server_params)
    server = utils.wait_for(server.id, cloud.nova.servers.get,
                            value="ACTIVE")
    return server


def setup_server_floating_ip(cloud, server):
    pool = "{}-pool".format(TEST_RESOURCE_PREFIX)
    ip_params = server._info["addresses"].get("novanetwork")
    if not ip_params:
        LOG.exception("Invalid network name, exiting")
        raise exceptions.Error
    ip = ip_params[0]
    floating_ips = cloud.nova.floating_ips_bulk.findall(instance_uuid=None)
    floating_ip = floating_ips[0]
    try:
        cloud.nova.servers.add_floating_ip(
            server.id,
            floating_ip.address,
            ip["addr"])
    except nova_excs.NotFound:
        LOG.exception("Floating IP not found: %s",
                      floating_ip._info)
        raise
    else:
        server = cloud.nova.servers.get(server)
        return server, floating_ip


def setup(events, cloud, target, num_tenants=0, num_servers=0, workloads={}):

    """Prepares test resources in the source cloud

    :param cloud:       an instance of Cloud, collection of clients to
                        OpenStack services.
    :param num_tenants: a number of tenants to create in the source cloud.
    :type num_tenants:  int
    :param num_servers: a number of servers to create per tenant
    :type servers:      int
    """

    prefix = TEST_RESOURCE_PREFIX
    test_clouds = {}
    test_tenant_clouds = {}
    tenants = workloads.get('tenants',
                            list(generate_tenants_list(num_tenants)))
    num_tenants = len(tenants)
    flavors = workloads.get('flavors',
                            list(generate_flavors_list(num_tenants)))
    images = workloads.get('images', list(generate_images_list(num_tenants)))
    for tenant_dict in tenants:
        servers = tenant_dict.get("servers",
                                  list(generate_servers_list(num_servers,
                                                             images,
                                                             flavors)))
        tenant_dict["servers"] = servers
    floating_ips = workloads.get(
        'floating_ips', list(generate_floating_ips_list(
            num_tenants * sum([len(t["servers"]) for t in tenants]))))
    # TODO(ogelbukh): add networks list here to support Neutron and VLAN
    # manager for nova network:
    # networks = workloads.get('networks',
    #                          generate_networks_list(num_tenants))
    for image_dict in images:
        image = setup_image(cloud, image_dict.copy())
        LOG.info("Created: %s", dict(image))
    for flavor_dict in flavors:
        flavor = cloud.nova.flavors.create(
            flavor_dict["name"],
            flavor_dict["ram"],
            flavor_dict["vcpu"],
            flavor_dict["disk"],
            is_public=True)
        LOG.info("Created: %s", flavor._info)
    if FLATDHCP:
        try:
            net = cloud.nova.networks.find(project_id=None)
        except nova_excs.NotFound:
            net = cloud.nova.networks.create(
                label="novanetwork",
                cidr="10.10.0.0/24",
                project_id=None)
            LOG.info("Created: %s", net._info)
        else:
            LOG.info("Already exists: %s", net._info)
    else:
        raise NotImplementedError()
    for pool in floating_ips:
        for poolname in pool:
            addr_list = pool[poolname]
            for addr in addr_list:
                floating_ip_dict = {"pool": poolname, "addr": addr}
                ip_range = setup_floating_ip(cloud, floating_ip_dict)
                LOG.info("Created: %s", ip_range._info)
    for tenant_dict in tenants:
        tenant = cloud.keystone.tenants.create(
            tenant_dict["name"],
            description=tenant_dict.get("description"))
        become_admin_in_tenant(cloud, cloud.keystone.auth_ref.user_id, tenant)
        tenant_cloud = cloud.restrict(tenant_name=tenant.name)
        test_tenant_clouds[tenant.id] = tenant_cloud
        setup_secgroup(tenant_cloud)
        user = cloud.keystone.users.create(
            name=tenant_dict["username"],
            password="default",
            tenant_id=tenant.id)
        LOG.info("Created: %s", user._info)
        user_cloud = cloud.restrict(username=user.name,
                                    password="default",
                                    tenant_name=tenant.name)
        LOG.info("Created: %s", tenant._info)
        events.emit("tenant create", {
            "cloud": target,
            "id": tenant.id,
            "name": tenant.name,
            "description": tenant.description,
        }, namespace="/events")
        for server_dict in tenant_dict["servers"]:
            server = setup_server(user_cloud, server_dict)
            LOG.info("Created server: %s", server._info)
            server, floating_ip = setup_server_floating_ip(cloud,
                                                           server)
            LOG.info("Assigned floating ip %s to server: %s",
                     floating_ip._info,
                     server._info)
            server = cloud.nova.servers.get(server)
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
