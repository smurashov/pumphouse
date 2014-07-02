import collections

from . import exceptions
from pumphouse.cloud import Namespace


class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


class Collection(object):
    def __init__(self, resource_class):
        self.resource_class = resource_class

    def __get__(self, obj, type):
        return obj.get_resource(self.resource_class)


class Resource(object):
    def __init__(self, cloud, objects):
        self.cloud = cloud
        self.objects = objects

    def list(self):
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



class Server(Resource):
    def create(self, name, image, flavor, nics=[]):
        addresses = {}
        for nic in nics:
            if nic["net-id"] not in addresses:
                addresses[nic["net-id"]] = []
                net = self.cloud.nova.networks.get(nic["net-id"])
            addresses[net.label].append({
                "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:c3:d8:d4",
                "version": 4,
                "addr": nic["v4-fixed-ip"],
                "OS-EXT-IPS:type": "fixed"
            })
        server = AttrDict(
{
 "OS-EXT-STS:task_state": None,
 "addresses": addresses,
 "image": {
    "id": image.id,
 },
 "OS-EXT-STS:vm_state": "active",
 "OS-EXT-SRV-ATTR:instance_name": "instance-00000004",
 "OS-SRV-USG:launched_at": "2014-06-26T12:48:18.000000",
 "flavor": {
  "id": flavor.id,
 },
 "id": "4a7318d7-8508-43a1-a7ea-1e228c71fc4d",
 "security_groups": [
  {
   "name": "default"
  }
 ],
 "user_id": "189f0c4c66fe4f2bb32238c7f0e32109",
 "OS-DCF:diskConfig": "MANUAL",
 "accessIPv4": "",
 "accessIPv6": "",
 "progress": 0,
 "OS-EXT-STS:power_state": 1,
 "OS-EXT-AZ:availability_zone": "nova",
 "config_drive": "",
 "status": "ACTIVE",
 "updated": "2014-06-26T12:48:18Z",
 "hostId": "9de0d0f05e277856424db23d54be4ea0d0bbcdce815ca08740f54609",
 "OS-EXT-SRV-ATTR:host": "ubuntu-1204lts-server-x86",
 "OS-SRV-USG:terminated_at": None,
 "key_name": None,
 "OS-EXT-SRV-ATTR:hypervisor_hostname": "ubuntu-1204lts-server-x86",
 "name": name,
 "created": "2014-06-26T12:48:06Z",
 "tenant_id": "7c825ee789b7416895e3bccf66edd05d",
 "os-extended-volumes:volumes_attached": [],
 "metadata": {}
}
)
        self.objects.append(server)
        return server


class Image(Resource):
    def data(self, id):
        data = AttrDict()
        data._resp = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        return data

    def create(self, **kwargs):
        image = AttrDict({
 "status": "active",
 "tags": [],
 "updated_at": "2014-06-26T12:48:05Z",
 "file": "/v2/images/8bda63f2-dbb3-40ff-a68c-5ba3462aa8c5/file",
 "owner": "7c825ee789b7416895e3bccf66edd05d",
 "id": "8bda63f2-dbb3-40ff-a68c-5ba3462aa8c5",
 "size": 13167616,
 "checksum": "64d7c1cd2b6f60c92c14662941cb7913",
 "created_at": "2014-06-26T12:48:04Z",
 "schema": "/v2/schemas/image"
},**kwargs
)
        self.objects.append(image)
        return image


class Network(Resource):
    def create(self, **kwargs):
        network = AttrDict({"vlan": kwargs["vlan_start"],
                            "vpn_private_address": kwargs["vpn_start"]},
                            **kwargs)
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
    pass


class SecGroup(Resource):
    def create(self, name, description):
        secgroup = AttrDict({'name': name,
                             'description': description})
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
        tenant = AttrDict({'name': name},
                          **kwargs)
        tenant._info = tenant
        self.objects.append(tenant)
        return tenant


class User(Resource):
    def create(self, **kwargs):
        user = AttrDict(**kwargs)
        user._info = user
        self.objects.append(user)
        return user


class Role(Resource):
    pass


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
    def __init__(self, cloud_ns, user_ns, identity):
        self.cloud_ns = cloud_ns
        self.user_ns = user_ns
        self.access_ns = cloud_ns.restrict(user_ns)
        self.data = {}
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
        return Cloud(self.cloud_nd, user_ns, self.identity)

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
        pass

    def push(self):
        """Push hashes of users' passwords."""
        pass

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

