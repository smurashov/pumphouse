import datetime
import random
import six
import string
import time
import uuid

from novaclient import exceptions as nova_excs
from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs

from . import cloud as pump_cloud
from . import exceptions
from . import management


class AttrDict(dict):
    def __init__(self, manager, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self
        self._info = self
        self.manager = manager


class TenantAttrDict(AttrDict):
    def list_users(self):
        return self.manager.list_users(self)


class Collection(object):
    def __init__(self, resource_class):
        self.resource_class = resource_class

    def __get__(self, obj, type):
        return obj.get_resource(self.resource_class)


class Resource(object):
    NotFound = Exception

    def __init__(self, cloud, objects):
        self.cloud = cloud
        self.objects = objects
        self.user_id = self._get_user_id(self.cloud.access_ns.username)
        self.tenant_id = self._get_tenant_id(self.cloud.access_ns.tenant_name)

    def list(self, search_opts=None, filters=None, tenant_id=None,
             project_id=None):
        for obj in self.objects:
            obj = self._update_status(obj)
        return self.objects

    findall = list

    def _update_status(self, obj):
        return obj

    def create(self, obj):
        self.objects.append(obj)

    def get(self, id):
        if isinstance(id, AttrDict):
            real_id = id['id']
        else:
            real_id = id
        for obj in self.objects:
            if obj.id == real_id:
                obj = self._update_status(obj)
                return obj
        raise self.NotFound("Not found: {}".format(id))

    def find(self, **kwargs):
        for obj in self.objects:
            for key, value in kwargs.iteritems():
                if obj[key] != value:
                    break
            else:
                return obj
        filter_str = ", ".join("{}={}".format(k, v)
                               for k, v in kwargs.iteritems())
        raise self.NotFound("Not found: {}".format(filter_str))

    def _findall(self, **kwargs):
        objects = []
        for obj in self.objects:
            for key, value in kwargs.iteritems():
                if obj[key] != value:
                    break
            else:
                objects.append(obj)
        return objects

    def delete(self, id):
        deleted = self.get(id)
        objects = [obj for obj in self.objects
                   if not obj.id == deleted.id]
        self.objects = objects

    def _get_user_id(self, username):
        for user in self.cloud.data['keystone']['users']:
            if user['name'] == username:
                return user['id']
        return None

    def _get_tenant_id(self, tenant_name):
        for tenant in self.cloud.data['keystone']['tenants']:
            if tenant['name'] == tenant_name:
                return tenant['id']
        raise exceptions.NotFound()


class NovaResource(Resource):
    NotFound = nova_excs.NotFound


class Server(NovaResource):
    def random_mac(self):
        mac = [0x00, 0x16, 0x3e,
               random.randint(0x00, 0x7f),
               random.randint(0x00, 0xff),
               random.randint(0x00, 0xff)]
        return ':'.join(map(lambda x: "%02x" % x, mac))

    def _update_status(self, server, status=None):
        if server.status == "BUILDING":
            updated = datetime.datetime.strptime(
                server.updated, "%Y-%m-%dT%H:%M:%S.%f")
            delta = datetime.datetime.now() - updated
            if delta.total_seconds() > 30:
                server.updated = datetime.datetime.now().isoformat()
                server.status = "ACTIVE"
        return server

    def create(self, name, image, flavor, nics=[]):
        addresses = {}
        server_uuid = uuid.uuid4()
        if isinstance(image, six.string_types):
            image_id = image
        else:
            image_id = image['id']
        if isinstance(flavor, int):
            flavor_id = flavor
        else:
            flavor_id = flavor['id']
        for nic in nics:
            net = self.cloud.nova.networks.get(nic["net-id"])
            if net['label'] not in addresses:
                addresses[net['label']] = []
            addresses[net['label']].append({
                "OS-EXT-IPS-MAC:mac_addr": self.random_mac(),
                "version": 4,
                "addr": nic["v4-fixed-ip"],
                "OS-EXT-IPS:type": "fixed"
            })
        server = AttrDict(self, {
            "OS-EXT-STS:task_state": None,
            "addresses": addresses,
            "image": {"id": image_id, },
            "OS-EXT-STS:vm_state": "active",
            "OS-EXT-SRV-ATTR:instance_name": "instance-00000004",
            "OS-SRV-USG:launched_at": datetime.datetime.now().isoformat(),
            "flavor": {"id": flavor_id, },
            "id": str(server_uuid),
            "security_groups": [{"name": "default"}],
            "user_id": self.user_id,
            "OS-DCF:diskConfig": "MANUAL",
            "accessIPv4": "",
            "accessIPv6": "",
            "progress": 0,
            "OS-EXT-STS:power_state": 1,
            "OS-EXT-AZ:availability_zone": "nova",
            "config_drive": "",
            "status": "BUILDING",
            "updated": datetime.datetime.now().isoformat(),
            "hostId": server_uuid.hex,
            "OS-EXT-SRV-ATTR:host": "ubuntu-1204lts-server-x86",
            "OS-SRV-USG:terminated_at": None,
            "key_name": None,
            "OS-EXT-SRV-ATTR:hypervisor_hostname":
                self.cloud.nova.schedule_server(),
            "name": name,
            "created": str(datetime.datetime.now()),
            "tenant_id": self.tenant_id,
            "os-extended-volumes:volumes_attached": [],
            "metadata": {}},
            add_floating_ip=self.add_floating_ip)
        self.objects.append(server)
        return server

    def add_floating_ip(self, floating_ip, fixed_ip=None):
        floating_ip_addr = {
            "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:c3:d8:d4",
            "version": 4,
            "addr": floating_ip,
            "OS-EXT-IPS:type": "floating"
        }
        floating_ip_list = self.cloud.data['nova']['floatingipbulks']
        for server in self.objects:
            for net in server["addresses"]:
                if not fixed_ip:
                    raise NotImplementedError
                for addr in server["addresses"][net]:
                    if addr['addr'] == fixed_ip:
                        server['addresses'][net].append(floating_ip_addr)
                        server._info = server
                        for ip in floating_ip_list:
                            if ip.address == floating_ip:
                                ip['instance_uuid'] = server["id"]
                        return server
        raise exceptions.NotFound

    def suspend(self, obj_id):
        server = self.get(obj_id)
        server.status = "SUSPENDED"
        server.update = datetime.datetime.now().isoformat()
        return server

    def resume(self, obj_id):
        server = self.get(obj_id)
        server.status = "ACTIVE"
        server.update = datetime.datetime.now().isoformat()
        return server


    def live_migrate(self, server_id, host, block_migration, disk_over_commit):
        if self.cloud.delays:
            time.sleep(random.randint(5, 10))
        server = self.get(server_id)
        server.status = "ACTIVE"
        server["OS-EXT-SRV-ATTR:hypervisor_hostname"] = \
            self.cloud.nova.schedule_server()
        server.update = datetime.datetime.now().isoformat()
        return server


class Image(Resource):
    def data(self, id):
        data = AttrDict(self)
        data._resp = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        return data

    def upload(self, image_id, data):
        if self.cloud.delays:
            time.sleep(random.randint(15, 45))

    def create(self, **kwargs):
        image_uuid = uuid.uuid4()
        image = AttrDict(self, {
            "status": "active",
            "tags": [],
            "updated_at": datetime.datetime.now().isoformat(),
            "file": "/v2/images/{}/file".format(str(image_uuid)),
            "owner": self.tenant_id,
            "id": str(image_uuid),
            "size": 13167616,
            "checksum": image_uuid.hex,
            "created_at": datetime.datetime.now().isoformat(),
            "schema": "/v2/schemas/image",
            "visibility": '',
            "min_ram": 0,
            "min_disk": 0,
            "protected": False},
            **kwargs)
        self.objects.append(image)
        return image


class Network(NovaResource):
    def create(self, **kwargs):
        net_uuid = uuid.uuid4()
        network = AttrDict(self, {
            "bridge": "br100",
            "vpn_public_port": None,
            "dhcp_start": "10.10.0.2",
            "bridge_interface": "eth0",
            "updated_at": str(datetime.datetime.now()),
            "id": str(net_uuid),
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
            "dns1": "8.8.4.4",
        }, **kwargs)
        network._info = network
        self.objects.append(network)
        return network


class Flavor(NovaResource):
    def create(self, name, ram, vcpus, disk, **kwargs):
        flavor_id = random.randint(0, 100)
        flavor = AttrDict(self, {
            "name": name,
            "ram": ram,
            "OS-FLV-DISABLED:disabled": False,
            "vcpus": vcpus,
            "swap": 0,
            "os-flavor-access:is_public": True,
            "rxtx_factor": 1.0,
            "OS-FLV-EXT-DATA:ephemeral": 0,
            "disk": disk,
            "id": flavor_id,
            "ephemeral": 0}, **kwargs)
        flavor._info = flavor
        self.objects.append(flavor)
        return flavor


class FloatingIP(NovaResource):
    def create(self, pool=None):
        self.objects = self.cloud.data['nova']['floatingipbulks']
        floating_ips = [obj for obj in self.objects if not obj.project_id]
        if len(floating_ips) < 1:
            raise self.NotFound()
        floating_ip = floating_ips[0]
        floating_ip['ip'] = floating_ip['address']
        floating_ip['project_id'] = self.tenant_id
        return floating_ip


class FloatingIPPool(NovaResource):
    pass


class FloatingIPBulk(NovaResource):
    def create(self, address, pool=None):
        floating_ip_uuid = uuid.uuid4()
        floating_ip = AttrDict(self, {
            "address": address,
            "id": str(floating_ip_uuid),
            "instance_uuid": None,
            "project_id": None,
            "pool": pool,
        })
        floating_ip._info = floating_ip
        self.objects.append(floating_ip)
        if "floatingippools" not in self.cloud.data["nova"]:
            self.cloud.data["nova"]["floatingippools"] = []
        self.cloud.data["nova"]["floatingippools"].append(
            AttrDict(self, {"name": pool}))
        return floating_ip


class SecGroup(NovaResource):
    def create(self, name, description):
        secgroup_uuid = uuid.uuid4()
        secgroup = AttrDict(self, {
            "name": name,
            "description": description,
            "id": str(secgroup_uuid),
            "rules": "",
            "tenant_id": self.tenant_id,
        })
        secgroup._info = secgroup
        self.objects.append(secgroup)
        return secgroup


class SecGroupRule(Resource):
    def create(self, id, **kwargs):
        rule = AttrDict(self, {
            "id": id,
            "ip_range": {
                "cidr": kwargs["cidr"],
            },
        }, **kwargs)
        rule._info = rule
        self.objects.append(rule)
        return rule


class Hypervisor(NovaResource):
    def search(self, hostname, servers=False):
        hypervs = []
        for hyperv in self.objects:
            if hyperv.name == hostname:
                hyperv = AttrDict(hyperv)
                if servers:
                    hyperv["servers"] = [
                        {"uuid": s.id}
                        for s in self.cloud.nova.servers.list()
                        if s["OS-EXT-SRV-ATTR:hypervisor_hostname"] == hostname
                    ]
                hypervs.append(hyperv)
        return hypervs


class Service(NovaResource):
    def list(self, host=None, binary=None):
        objects = [obj
                   for obj in self.objects
                   if (host is not None and obj.host == host or
                       binary is not None and obj.binary == binary)]
        return objects

    def disable(self, hostname, binary):
        service = self.find(host=hostname, binary=binary)
        service.status = "disbled"
        return service

    def enable(self, hostname, binary):
        service = self.find(host=hostname, binary=binary)
        service.status = "enabled"
        return service


class KeystoneResource(Resource):
    NotFound = keystone_excs.NotFound


class Tenant(KeystoneResource):
    def create(self, name, **kwargs):
        tenant_uuid = uuid.uuid4()
        tenant = TenantAttrDict(self, {
            "name": name,
            "id": str(tenant_uuid),
            "enabled": True,
        }, **kwargs)
        self.objects.append(tenant)
        return tenant

    def add_user(self, tenant, user, role):
        pass

    def list_users(self, tenant):
        return [user
                for user in self.cloud.keystone.users.list()
                if user.tenantId == tenant.id]


class User(KeystoneResource):
    def create(self, **kwargs):
        user_uuid = uuid.uuid4()
        user = AttrDict(self, {
            "id": str(user_uuid),
            "tenantId": kwargs["tenant_id"],
            "username": kwargs["name"],
            "enabled": True
        }, **kwargs)
        self.objects.append(user)
        return user


class Role(KeystoneResource):
    def create(self, name):
        role_uuid = uuid.uuid4()
        role = AttrDict(self, {
            "id": str(role_uuid),
            "name": name,
        })
        self.objects.append(role)
        return role

    def add_user_role(self, user_id, role_id, tenant):
        for role in self.objects:
            if role["id"] == role_id:
                break
        for user in self.cloud.data['keystone']['users']:
            if user["id"] == user_id:
                if 'roles' in user:
                    user['roles'].append(role)
                else:
                    user['roles'] = [role]
                return
        raise exceptions.NotFound()

    def roles_for_user(self, user_id, **kwargs):
        for user in self.cloud.data['keystone']['users']:
            if user['id'] == user_id:
                return user['roles']
        raise exceptions.NotFound()


class AuthRef(KeystoneResource):
    pass


class BaseService(object):
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


class Nova(BaseService):
    servers = Collection(Server)
    flavors = Collection(Flavor)
    networks = Collection(Network)
    floating_ips = Collection(FloatingIP)
    floating_ips_bulk = Collection(FloatingIPBulk)
    floating_ip_pools = Collection(FloatingIPPool)
    security_groups = Collection(SecGroup)
    hypervisors = Collection(Hypervisor)
    services = Collection(Service)

    def schedule_server(self):
        services = self.services._findall(status="enabled",
                                          state="up",
                                          binary="nova-compute")
        service = random.choice(services)
        return service.host


class Glance(BaseService):
    images = Collection(Image)


class Keystone(BaseService):
    tenants = Collection(Tenant)
    users = Collection(User)
    roles = Collection(Role)
    auth_ref = Collection(AuthRef)


class Cloud(object):
    def __init__(self, cloud_ns, user_ns, identity, data=None):
        self.delays = False
        self.cloud_ns = cloud_ns
        self.user_ns = user_ns
        self.access_ns = cloud_ns.restrict(user_ns)
        self.data = data or {}
        self.nova = Nova(self)
        self.keystone = Keystone(self)
        self.glance = Glance(self)
        if not data:
            admin_tenant = AttrDict(self.keystone, {
                "name": self.access_ns.tenant_name,
                "id": str(uuid.uuid4()),
            }, description="admin")
            admin_role = AttrDict(self.keystone, {
                "name": "admin",
                "id": str(uuid.uuid4()),
            })
            admin_user = AttrDict(self.keystone, {
                "username": self.access_ns.username,
                "name": self.access_ns.username,
                "id": str(uuid.uuid4()),
                "roles": [admin_role],
                "tenantId": admin_tenant.id,
                "enabled": True,
            })
            self.data["keystone"]["tenants"] = [admin_tenant]
            self.data["keystone"]["roles"] = [admin_role]
            self.data["keystone"]["users"] = [admin_user]
            hostname_prefix = "".join(random.choice(string.ascii_uppercase)
                                      for i in (0, 0))
            services = [AttrDict(self.nova, {
                "host": "pumphouse-{0}-{1}".format(hostname_prefix, i),
                "binary": "nova-compute",
                "state": "up",
                "status": "enabled",
            }) for i in range(2)]
            hypervs = [AttrDict(self.nova, {
                "name": s.host,
                "service": s,
            }) for s in services]
            secgroups = [AttrDict(self.nova, {
                "name": "default",
                "description": "default",
                "tenant_id": admin_tenant.id,
                "id": str(uuid.uuid4()),
                "rules": "",
            })]
            self.data["nova"]["services"] = services
            self.data["nova"]["hypervisors"] = hypervs
            self.data["nova"]["secgroups"] = secgroups
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
        cloud_ns = pump_cloud.Namespace(auth_url=endpoint["auth_url"])
        user_ns = pump_cloud.Namespace(
            username=endpoint["username"],
            password=endpoint["password"],
            tenant_name=endpoint["tenant_name"],
        )
        return cls(cloud_ns, user_ns, identity)

    def __repr__(self):
        return "<Cloud(namespace={!r})>".format(self.access_ns)


class Identity(object):
    def __init__(self, connection):
        pass

    def fetch(self, user_id):
        pass

    def push(self):
        pass

    def __iter__(self):
        return iter(())

    def update(self, iterable):
        pass


def make_client(config, target, cloud_driver, identity_driver):
    cloud = pump_cloud.make_client(config, target, cloud_driver,
                                   identity_driver)
    if target == "source":
        parameters = config.get("fake", {})
        num_tenants = parameters.get("num_tenants", 2)
        num_servers = parameters.get("num_servers", 2)
        management.setup(cloud, num_tenants, num_servers)
        delays = parameters.get("delays", False)
        cloud.delays = delays
    return cloud
