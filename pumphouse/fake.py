import collections
import datetime
import random
import six
import uuid

from . import exceptions
from novaclient import exceptions as nova_excs
from keystoneclient.openstack.common.apiclient import exceptions as keystone_excs
from glanceclient.openstack.common.apiclient import exceptions as glance_excs
from pumphouse.cloud import Namespace


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self
        self._info = self


class Collection(object):
    def __init__(self, resource_class):
        self.resource_class = resource_class

    def __get__(self, obj, type):
        return obj.get_resource(self.resource_class)


class Resource(object):
    def __init__(self, cloud, objects):
        self.cloud = cloud
        self.objects = objects
        self.user_id = self._get_user_id(self.cloud.access_ns.username)
        self.tenant_id = self._get_tenant_id(self.cloud.access_ns.tenant_name)

    def list(self, search_opts=None, filters=None, tenant_id=None):
        return self.objects

    findall = list

    def create(self, obj):
        self.objects.append(obj)

    def get(self, id):
        for obj in self.objects:
            if obj.id == id:
                return obj
        raise exceptions.NotFound()

    def find(self, **kwargs):
        for key in kwargs:
            for obj in self.objects:
                if obj[key] == kwargs[key]:
                    return obj
            raise exceptions.NotFound()

    def _get_user_id(self, username):
        for user in self.cloud.data['keystone']['users']:
            if user['name'] == username:
                return user['id']
        raise exceptions.NotFound

    def _get_tenant_id(self, tenant_name):
        for tenant in self.cloud.data['keystone']['tenants']:
            if tenant['name'] == tenant_name:
                return tenant['id']
        raise exceptions.NotFound


class Server(Resource):
    def random_mac(self):
        mac = [ 0x00, 0x16, 0x3e,
                random.randint(0x00, 0x7f),
                random.randint(0x00, 0xff),
                random.randint(0x00, 0xff) ]
        return ':'.join(map(lambda x: "%02x" % x, mac))

    def create(self, name, image, flavor, nics=[]):
        addresses = {}
        for nic in nics:
            if nic["net-id"] not in addresses:
                addresses[nic["net-id"]] = []
                net = self.cloud.nova.networks.get(nic["net-id"])
            addresses[net.label].append({
                "OS-EXT-IPS-MAC:mac_addr": self.random_mac(),
                "version": 4,
                "addr": nic["v4-fixed-ip"],
                "OS-EXT-IPS:type": "fixed"
            })
        server = AttrDict(
{
 "OS-EXT-STS:task_state": None,
 "addresses": addresses,
 "image": {
    "id": image["id"],
 },
 "OS-EXT-STS:vm_state": "active",
 "OS-EXT-SRV-ATTR:instance_name": "instance-00000004",
 "OS-SRV-USG:launched_at": str(datetime.datetime.now()),
 "flavor": {
  "id": flavor["id"],
 },
 "id": str(self.id),
 "security_groups": [
  {
   "name": "default"
  }
 ],
 "user_id": self.user_id,
 "OS-DCF:diskConfig": "MANUAL",
 "accessIPv4": "",
 "accessIPv6": "",
 "progress": 0,
 "OS-EXT-STS:power_state": 1,
 "OS-EXT-AZ:availability_zone": "nova",
 "config_drive": "",
 "status": "ACTIVE",
 "updated": "2014-06-26T12:48:18Z",
 "hostId": self.id.hex,
 "OS-EXT-SRV-ATTR:host": "ubuntu-1204lts-server-x86",
 "OS-SRV-USG:terminated_at": None,
 "key_name": None,
 "OS-EXT-SRV-ATTR:hypervisor_hostname": "ubuntu-1204lts-server-x86",
 "name": name,
 "created": "2014-06-26T12:48:06Z",
 "tenant_id": self.tenant_id,
 "os-extended-volumes:volumes_attached": [],
 "metadata": {}
}
)
        self.objects.append(server)
        return server

    def add_floating_ip(self, floating_ip, fixed_ip):
        floating_ip_addr = {
            "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:c3:d8:d4",
            "version": 4,
            "addr": floating_ip,
            "OS-EXT-IPS:type": "floating"
        }
        for server in self.objects:
            for net in server["addresses"]:
                for addr in net:
                    if addr['addr'] == fixed_ip:
                        net.append(floating_ip_addr)
                        server._info = server
                        for ip in self.cloud.data['nova']['floatingipsbulk']:
                            if ip['addr'] == floating_ip:
                                ip['instance_uuid'] = server["id"]
                        return server
        raise exceptions.NotFound


class Image(Resource):
    def data(self, id):
        data = AttrDict()
        data._resp = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        return data

    def create(self, **kwargs):
        image = AttrDict({
 "status": "active",
 "tags": [],
 "updated_at": str(datetime.datetime.now()),
 "file": "/v2/images/{}/file".format(str(self.id)),
 "owner": self.tenant_id,
 "id": str(self.id),
 "size": 13167616,
 "checksum": self.id.hex,
 "created_at": "2014-06-26T12:48:04Z",
 "schema": "/v2/schemas/image"
},**kwargs
)
        self.objects.append(image)
        return image


class Network(Resource):
    def create(self, **kwargs):
        network = AttrDict({
 "bridge": "br100",
 "vpn_public_port": None,
 "dhcp_start": "10.10.0.2",
 "bridge_interface": "eth0",
 "updated_at": str(datetime.datetime.now()),
 "id": str(self.id),
 "cidr_v6": None,
 "deleted_at": None,
 "gateway": "10.10.0.1",
 "rxtx_base": None,
 "priority": None,
 "project_id": self.tenant_id,
 "vpn_private_address": None,
 "deleted": 0,
 "vlan": 390,
 "broadcast": "10.10.0.255",
 "netmask": "255.255.255.0",
 "injected": False,
 "cidr": "10.10.0.0/24",
 "vpn_public_address": None,
 "multi_host": False,
 "dns2": None,
 "created_at": str(datetime.datetime.now()),
 "host": "ubuntu-1204lts-server-x86",
 "gateway_v6": None,
 "netmask_v6": None,
 "dns1": "8.8.4.4"
}, **kwargs)
        network._info = network
        self.objects.append(network)
        return network


class Flavor(Resource):
    def create(self, name, ram, vcpus, disk, **kwargs):
        flavor = AttrDict({"name": name,
                           "ram": ram,
                           "OS-FLV-DISABLED:disabled": False,
                           "vcpus": vcpus,
                           "swap": kwargs["swap"],
                           "os-flavor-access:is_public": kwargs["is_public"],
                           "rxtx_factor": kwargs["rxtx_factor"],
                           "OS-FLV-EXT-DATA:ephemeral": 0,
                           "disk": disk, 
                           "id": kwargs["flavorid"]})
        flavor._info = flavor
        self.objects.append(flavor)
        return flavor


class FloatingIP(Resource):
    pass


class FloatingIPPool(Resource):
    pass


class FloatingIPBulk(Resource):
    def create(self, address, pool=None):
        floating_ip = AttrDict({'address': address,
                                'id': str(self.id),
                                'instance_uuid': None,
                                'project_id': None,
                                'pool': pool})
        floating_ip._info = floating_ip
        self.objects.append(floating_ip)
        return floating_ip


class SecGroup(Resource):
    def create(self, name, description):
        secgroup = AttrDict({'name': name,
                             'description': description,
                             'id': str(self.id)})
        secgroup._info = secgroup
        self.objects.append(secgroup)
        return secgroup


class SecGroupRule(Resource):
    def create(self, id, **kwargs):
        rule = AttrDict({'id': id,
                         'ip_range': {
                             'cidr': kwargs['cidr']
                         }
                        }, **kwargs)
        rule._info = rule
        self.objects.append(rule)
        return rule


class Tenant(Resource):
    def create(self, name, **kwargs):
        tenant = AttrDict({'name': name,
                           'id': str(self.id)},
                          **kwargs)
        tenant._info = tenant
        self.objects.append(tenant)
        return tenant


class User(Resource):
    def create(self, **kwargs):
        user = AttrDict({'id': str(self.id),
                         'tenantId': kwargs['tenant_id'],
                         'username': kwargs['name']},
                         **kwargs)
        user._info = user
        self.objects.append(user)
        return user


class Role(Resource):
    def create(self, name):
        role = AttrDict({'id': str(self.id), 'name': name})
        role._info = role
        self.objects.append(role)
        return role

    def add_user_role(self, user_id, role_id, tenant):
        for role in self.objects:
            if role['id'] == role_id:
                break
        for user in self.cloud.data['keystone']['users']:
            if user['id'] == user_id:
                if user['roles']:
                    user['roles'].append(role)
                else:
                    user['roles'] = [role,]
                return
        raise exceptions.NotFound

    def roles_for_user(self, user_id, **kwargs):
        for user in self.cloud.data['keystone']['users']:
            if user['id'] == user_id:
                return user['roles']
        raise exceptions.NotFound


class Service(object):
    def __init__(self, cloud):
        self.cloud = cloud
        service_name = self.__class__.__name__.lower()
        self.resources_objects = cloud.get_service(service_name)
        self.resources = {}

    def get_resource(self, resource_class):
        if resource_class in self.resources:
            return self.resources[resource_class]
        resource_name = "{}s".format(resource_class.__name__.lower())
        objects = self.resources_objects.setdefault(resource_name, [])
        self.resources[resource_class] = resource = resource_class(self.cloud,
                                                                   objects)
        return resource


class Nova(Service):
    servers = Collection(Server)
    flavors = Collection(Flavor)
    networks = Collection(Network)
    floating_ips = Collection(FloatingIP)
    floating_ips_bulk = Collection(FloatingIPBulk)
    floating_ip_pools = Collection(FloatingIPPool)
    security_groups = Collection(SecGroup)


class Glance(Service):
    images = Collection(Image)


class Keystone(Service):
    tenants = Collection(Tenant)
    users = Collection(User)
    roles = Collection(Role)


class Cloud(object):
    def __init__(self, cloud_ns, user_ns, identity, data=None):
        self.cloud_ns = cloud_ns
        self.user_ns = user_ns
        self.access_ns = cloud_ns.restrict(user_ns)
        if not data:
            self.data = {
                         'glance': {},
                         'keystone': {
                            'tenants': [{
                                'name': self.access_ns.tenant_name,
                                'id': str(uuid.uuid4())
                                }],
                            'users': [{
                                'username': self.access_ns.username,
                                'name': self.access_ns.username,
                                'id': str(uuid.uuid4())
                            }]},
                         'nova': {}
                        }
        else:
            self.data = data
        self.nova = Nova(self)
        self.keystone = Keystone(self)
        self.glance = Glance(self)
        if isinstance(identity, Identity):
            self.identity = identity
        else:
            self.identity = Identity(**identity)

    def get_service(self, service_name):
        return self.data.setdefault(service_name, {})

    def restrict(self, user_ns):
        return Cloud(self.cloud_ns, user_ns, self.identity, self.data)

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


class Identity(collections.Mapping):
    def __init__(self, connection):
        self.hashes = {
            "83f8d6ed75c2468e9c469bd2afb1458e": "$6$rounds=40000$Q4G5USdnoMc1QEAL$ZTnaXlsojr6Ax5wmKT3RNmlRMFkoJ3ZpWRr2fYVC2b1RC61N03/AgmW4OhoP0ugSdz70XlMPZ5sw80ivgAAcO1",
            "97e9a411cc204cf48cc885579e8090f8": "$6$rounds=40000$9WoWkC9aFenmPmQp$KVd/Sm2CIVSmaG.DmUCJQcVVysCArDKDq8FJwAQ.csAktmCtJ4GBa9bCDP/p/Ydaf0vjQFmSku13fPBXmlcxW."
            }

    def fetch(self, user_id):
        """Fetch a hash of user's password."""
        return self.hashes[user_id]

    def push(self):
        """Push hashes of users' passwords."""
        return

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

