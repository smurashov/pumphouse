import collections

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self


class Resource(object):
    def __init__(self, objs):
        self.objs = objs
        self.resource_class = self.__class__.__name__

    def __get__(self, obj, type):
        return self

    def list(self):
        return self.objs

    def create(self, obj):
        self.objs.append(obj)

    def get(self, id):
        for obj in self.objs:
            if obj.id == id:
                return obj
        raise Exception

    find = get
    findall = list


class Server(Resource):
    def create(self, name, image, flavor, nics=[]):
        addresses = {}
        for nic in nics:
            if nic["net-id"] not in addresses:
                addresses[nic["net-id"]] = []
            addresses[nic["net-id"]].append({
                "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:c3:d8:d4",
                "version": 4,
                "addr": nic["v4-fixed-ip"],
                "OS-EXT-IPS:type": "fixed"
            })
        server = AttrDict(
{
 "OS-EXT-STS:task_state": null,
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
 "OS-SRV-USG:terminated_at": null,
 "key_name": null,
 "OS-EXT-SRV-ATTR:hypervisor_hostname": "ubuntu-1204lts-server-x86",
 "name": name,
 "created": "2014-06-26T12:48:06Z",
 "tenant_id": "7c825ee789b7416895e3bccf66edd05d",
 "os-extended-volumes:volumes_attached": [],
 "metadata": {}
}
)
        self.objs.append(server)
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
        self.objs.append(image)
        return image


class Network(Resource):
    pass

class Flavor(Resource):
    def create(self, name, ram, vcpus, disk, **kwargs):
        flavor = AttrDict({"name": name,
                           "ram": ram,
                           "OS-FLV-DISABLED:disabled": false,
                           "vcpus": vcpus,
                           "swap": kwargs["swap"],
                           "os-flavor-access:is_public": kwargs["is_public"],
                           "rxtx_factor": kwargs["rxtx_factor"],
                           "OS-FLV-EXT-DATA:ephemeral": 0,
                           "disk": disk, 
                           "id": kwargs["flavorid"]})
        flavor._info = flavor
        self.objs = flavor
        return flavor
                

class FloatingIP(Resource):
    pass


class FloatingIPPool(Resource):
    pass


class FloatingIPBulk(Resource):
    pass


class SecGroup(Resource):
    pass


class Tenant(Resource):
    pass


class User(Resource):
    pass


class Role(Resource):
    pass


class Nova(object):
    servers = Server()
    flavors = Flavor()
    networks = Network([])
    floating_ips = FloatingIP()
    floating_ips_bulk = FloatingIPBulk()
    floating_ip_pools = FloatingIPPool()
    security_groups = SecGroup()

    def __init__(self, data):
        self.data = data


class Glance(object):
    images = Image([])


class Keystone(object):
    tenants = Tenant([])
    users = User([])
    roles = Role([])


class Cloud(object):
    def __init__(self, cloud_ns, user_ns, identity):
        self.cloud_ns = cloud_ns
        self.user_ns = user_ns
        self.access_ns = cloud_ns.restrict(user_ns)
        self.data = {}
        self.nova = Nova(self.data)
        self.keystone = Keystone(self.data)
        self.glance = Glance(self.data)
        if isinstance(identity, Identity):
            self.identity = identity
        else:
            self.identity = Identity(**identity)


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

