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
import random
import urllib
import tempfile

from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs
from novaclient import exceptions as nova_excs

from pumphouse import exceptions
from pumphouse import utils
from pumphouse import plugin

LOG = logging.getLogger(__name__)

RO_SECURITY_GROUPS = ['default']
TEST_IMAGE_URL = ("http://download.cirros-cloud.net/0.3.2/"
                  "cirros-0.3.2-x86_64-disk.img")
TEST_IMAGE_FILE = '/tmp/cirros-0.3.2.img'
TEST_RESOURCE_PREFIX = "pumphouse"
FLOATING_IP_STRING = "172.16.0.{}"
network_manager = plugin.Plugin("network_manager", default="FlatDHCP")
network_generator = plugin.Plugin("network_generator", default="FlatDHCP")


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
                       stop_excs=(nova_excs.NotFound,))
        LOG.info("Deleted server: %s", server._info)
        hostname = getattr(server, "OS-EXT-SRV-ATTR:hypervisor_hostname")
        events.emit("server terminate", {
            "cloud": target,
            "id": server.id,
            "host_name": hostname
        }, namespace="/events")

    for flavor in cloud.nova.flavors.list():
        if is_prefixed(flavor.name):
            cloud.nova.flavors.delete(flavor)
            LOG.info("Deleted flavor: %s", flavor._info)
            events.emit("flavor delete", {
                "cloud": target,
                "id": flavor.id,
            }, namespace="/events")

    if (cloud.cinder):
        for volume in cloud.cinder.volumes.list(
                search_opts={'all_tenants': 1}):
            vol_name = volume._info['display_name']
            vol_id = volume._info['id']
            if vol_name and is_prefixed(vol_name):
                cloud.cinder.volumes.delete(vol_id)

                LOG.info("Delete volume: %s", str(volume._info))
                events.emit("volume delete", {
                    "cloud": target,
                    "id": vol_id
                }, namespace="/events")

    for image in cloud.glance.images.list():
        if not is_prefixed(image.name):
            continue
        cloud.glance.images.delete(image.id)
        LOG.info("Deleted image: %s", dict(image))
        events.emit("image delete", {
            "cloud": target,
            "id": image.id
        }, namespace="/events")

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
        events.emit("secgroup delete", {
            "cloud": target,
            "id": secgroup.id
        }, namespace="/events")

    for floating_ip in cloud.nova.floating_ips_bulk.list():
        cloud.nova.floating_ips_bulk.delete(floating_ip.address)
        LOG.info("Deleted floating ip: %s", floating_ip._info)
        events.emit("floating_ip delete", {
            "cloud": target,
            "id": floating_ip.address
        }, namespace="/events")

    net_service = False
    try:
        net_service = cloud.keystone.services.find(type="network")
    except exceptions.keystone_excs.NotFound:
        pass
    if (net_service):
        networks = cloud.neutron.list_networks()['networks']
        routers = cloud.neutron.list_routers()['routers']

        for net in networks:
            for router in routers:
                subnets = cloud.neutron.list_subnets(
                    network_id=net['id'])['subnets']
                for subnet in subnets:
                    try:
                        cloud.neutron.remove_interface_router(
                            router['id'], {'subnet_id': subnet['id']})
                    except:
                        pass

                cloud.neutron.remove_gateway_router(router['id'])
                cloud.neutron.delete_router(router['id'])

        for port in cloud.neutron.list_ports()['ports']:
            LOG.info("Deleted network: %s", port['id'])
            cloud.neutron.delete_port(port['id'])

        for subnet in cloud.neutron.list_subnets()['subnets']:
            LOG.info("Deleted subnet: %s", subnet['name'])
            cloud.neutron.delete_subnet(subnet['id'])

        for network in cloud.neutron.list_networks()['networks']:
            LOG.info("Delete network: %s", network['name'])
            cloud.neutron.delete_network(network['id'])

            LOG.info("Deleted network: %s", network._info)
            events.emit("network delete", {
                "cloud": target,
                "id": network['id']
            }, namespace="/events")

    for network in cloud.nova.networks.list():
        if not is_prefixed(network.label):
            continue
        cloud.nova.networks.disassociate(network)
        cloud.nova.networks.delete(network)
        LOG.info("Deleted network: %s", network._info)
        events.emit("network delete", {
            "cloud": target,
            "id": network.id
        }, namespace="/events")

    for user in cloud.keystone.users.list():
        if is_prefixed(user.name):
            cloud.keystone.users.delete(user)
            LOG.info("Deleted user: %s", user._info)
            events.emit("user delete", {
                "cloud": target,
                "id": user.id
            }, namespace="/events")

    for role in cloud.keystone.roles.list():
        if is_prefixed(role.name):
            cloud.keystone.roles.delete(role)
            LOG.info("Deleted role: %s", role._info)
            events.emit("role delete", {
                "cloud": target,
                "id": role.id
            }, namespace="/events")

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
    flavor_ref = str(random.randint(1, 0x7fffffff))
    yield {"name": "{}-flavor-{}"
           .format(TEST_RESOURCE_PREFIX, flavor_ref),
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
    pool_ref = str(random.randint(1, 0x7fffffff))
    pool = "{}-pool-{}".format(TEST_RESOURCE_PREFIX, pool_ref)
    addr_list = [FLOATING_IP_STRING.format(136 + i) for i in xrange(num)]
    yield {pool: addr_list}


@network_generator.add("FlatDHCP")
def generate_flat_networks_list(num):
    yield {
        "label": "novanetwork",
        "cidr": "10.10.0.0/24",
        "project_id": None
    }


@network_generator.add("VLAN")
def generate_vlan_networks_list(num):
    for i in xrange(num):
        yield {
            "label": "{}-{}".format(TEST_RESOURCE_PREFIX, i),
            "cidr": "10.42.{}.0/24".format(i),
            "vlan": "20{}".format(i + 3)
        }


def generate_neutron_subnet_list():
    yield {
        'subnets': [
            {
                'cidr': '192.168.199.0/24',
                'ip_version': 4,
            }
        ]
    }


def generate_images_list(num):
    image_ref = str(random.randint(1, 0x7fffffff))
    yield {"name": "{}-image-{}".format(TEST_RESOURCE_PREFIX, image_ref),
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


def generate_volumes_list(num):
    for i in xrange(num):
        volume_ref = str(random.randint(1, 0x7fffffff))
        yield {"size": 1,
               "display_name": "{}-{}".format(TEST_RESOURCE_PREFIX,
                                              volume_ref)}


def _create_networks(events, cloud, networks):
    for network_dict in networks:
        try:
            net = cloud.nova.networks.create(**network_dict)
        except exceptions.nova_excs.Conflict:
            net = cloud.nova.networks.find(cidr=network_dict["cidr"])
            LOG.info("Already exists: %s", net._info)
        else:
            LOG.info("Created: %s", net._info)
            events.emit("network created", {
                "id": net.id,
                "name": net.label,
                "cloud": "source",
            }, namespace="/events")


@network_manager.add("FlatDHCP")
def setup_network_flatdhcp(events, cloud, networks):
    for net in cloud.nova.networks.findall(project_id=None):
        if net.label == "novanetwork":
            LOG.info("Already exists: %s", net._info)
            return
    else:
        _create_networks(events, cloud, networks)


@network_manager.add("VLAN")
def setup_network_vlans(events, cloud, networks):
    _create_networks(events, cloud, networks)


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
                                   open(image_file, "rb"))
    return image


def setup_neutron_network(cloud, net_name, subnet, port):
    # TODO (sryabin) try/except NetworkExists
    network = cloud.neutron.create_network(body={
        'network': {
            'name': net_name,
            'admin_state_up': True
        }
    })['network']

    port['network_id'] = subnet['network_id'] = network['id']

    sub_network = cloud.neutron.create_subnet(body={
        'subnet': [{subnet}]
    })['subnet']

    cloud.neutron.create_port(body={
        'port': {port}
    })


def cache_image_file(url=TEST_IMAGE_URL):
    _, path = tempfile.mkstemp()
    LOG.info("Caching test image from %s: %s", url, path)
    urllib.urlretrieve(url, path)
    return path


def setup_volume(cloud, volume_dict):
    LOG.info("Create volume: %s", str(volume_dict))
    return cloud.cinder.volumes.create(**volume_dict)


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
    fixed_ips = [server.addresses[ip_params][0]
                 for ip_params in server.addresses
                 if server.addresses[ip_params][0]["OS-EXT-IPS:type"] ==
                 "fixed"]
    fixed_ip = fixed_ips[0]
    floating_ips = cloud.nova.floating_ips_bulk.findall(instance_uuid=None)
    floating_ip = floating_ips[0]
    try:
        cloud.nova.servers.add_floating_ip(
            server.id,
            floating_ip.address,
            fixed_ip["addr"])
    except nova_excs.NotFound:
        LOG.exception("Floating IP not found: %s",
                      floating_ip._info)
        raise
    else:
        server = cloud.nova.servers.get(server)
        return server, floating_ip


def setup(plugins, events, cloud, target,
          num_tenants=0, num_servers=0, num_volumes=0, workloads={}):

    """Prepares test resources in the source cloud

    :param cloud:       an instance of Cloud, collection of clients to
                        OpenStack services.
    :param num_tenants: a number of tenants to create in the source cloud.
    :type num_tenants:  int
    :param num_servers: a number of servers to create per tenant
    :type num_servers:  int
    :param num_volumes: a number of volumes to create per tenant
    :type num_volumes:  int
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
        volumes = workloads.get("volumes",
                                list(generate_volumes_list(num_volumes)))
        tenant_dict["volumes"] = volumes

    floating_ips = workloads.get(
        'floating_ips', list(generate_floating_ips_list(
            num_tenants * sum([len(t["servers"]) for t in tenants]))))
    generate_networks_list = network_generator.select_from_config(plugins)
    networks = workloads.get('networks',
                             generate_networks_list(num_tenants))
    for image_dict in images:
        image = setup_image(cloud, image_dict.copy())
        LOG.info("Created: %s", dict(image))
        events.emit("image created", {
            "id": image["id"],
            "name": image["name"],
            "cloud": target
        }, namespace="/events")

    for flavor_dict in flavors:
        flavor = cloud.nova.flavors.create(
            flavor_dict["name"],
            flavor_dict["ram"],
            flavor_dict["vcpu"],
            flavor_dict["disk"],
            is_public=True)
        LOG.info("Created: %s", flavor._info)
        events.emit("flavor created", {
            "id": flavor.id,
            "name": flavor.name,
            "cloud": target
        }, namespace="/events")

    setup_network = network_manager.select_from_config(plugins)
    setup_network(events, cloud, networks)

    for pool in floating_ips:
        for poolname in pool:
            addr_list = pool[poolname]
            for addr in addr_list:
                floating_ip_dict = {"pool": poolname, "addr": addr}
                ip_range = setup_floating_ip(cloud, floating_ip_dict)
                LOG.info("Created: %s", ip_range._info)
                events.emit("floating_ip created", {
                    "id": addr,
                    "cloud": target
                }, namespace="/events")

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

        for volume_dict in tenant_dict["volumes"]:
            try:
                volume = setup_volume(user_cloud, volume_dict)
            except Exception as exc:
                LOG.exception("Exception: %s", exc.message)
                raise exc
            tries = []
            while volume.status != 'available':
                volume = user_cloud.cinder.volumes.get(volume.id)
                tries.append(volume)
                if len(tries) > 30:
                    LOG.exception("Volume not available in time: %s",
                                  str(volume._info))
                    raise exceptions.TimeoutException()
            LOG.info("Created: %s", str(volume._info))
            events.emit("volume create", {
                "cloud": target,
                "id": volume._info["id"],
                "status": "active",
                "display_name": volume._info["display_name"],
                "tenant_id": volume._info["os-vol-tenant-attr:tenant_id"],
                "host_id": volume._info.get("os-vol-host-attr:host"),
                "attachment_server_ids": [],
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

            events.emit("floating_ip assigned", {
                "id": floating_ip.address,
                "server_id": server.id,
                "cloud": target
            }, namespace="/events")
