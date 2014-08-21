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

import datetime
import random
import six
import string
import time
import uuid

from novaclient import exceptions as nova_excs
from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs

from . import base
from . import cloud as pump_cloud
from . import exceptions


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
        self.user_id = self._get_user_id(self.cloud.namespace.username)
        self.tenant_id = self._get_tenant_id(self.cloud.namespace.tenant_name)

    def list(self, search_opts=None, filters=None, tenant_id=None,
             project_id=None, instance_uuid=None):
        for obj in self._iterate_values():
            self._update_status(obj)
        return self.objects.values()

    findall = list

    def _update_status(self, obj):
        return obj

    def create(self, obj):
        self.objects[obj.id] = obj

    def get(self, id):
        if isinstance(id, AttrDict):
            real_id = id['id']
        else:
            real_id = id
        for obj_id, obj in self.objects.iteritems():
            if obj_id == real_id:
                obj = self._update_status(obj)
                return obj
        raise self.NotFound("Not found: {}".format(id))

    def find(self, **kwargs):
        for obj in self._iterate_values():
            for key, value in kwargs.iteritems():
                if obj[key] != value:
                    break
            else:
                return obj
        filter_str = ", ".join("{}={}".format(k, v)
                               for k, v in kwargs.iteritems())
        raise self.NotFound("Not found: {}".format(filter_str))

    def _iterate_values(self):
        if isinstance(self.objects, list):
            return self.objects
        return self.objects.itervalues()

    def _findall(self, **kwargs):
        objects = []
        for obj in self._iterate_values():
            for key, value in kwargs.iteritems():
                if obj[key] != value:
                    break
            else:
                objects.append(obj)
        return objects

    def delete(self, obj):
        if hasattr(obj, "id"):
            obj_id = obj.id
        else:
            obj_id = obj
        self.objects.pop(obj_id, None)

    def _get_user_id(self, username):
        users_dict = self.cloud.data['keystone']['users']
        for user_id, user in users_dict.iteritems():
            if user['name'] == username:
                return user_id
        return

    def _get_tenant_id(self, tenant_name):
        tenants_dict = self.cloud.data['keystone']['tenants']
        for tenant_id, tenant in tenants_dict.iteritems():
            if tenant['name'] == tenant_name:
                return tenant_id
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
            if not self.cloud.delays or delta.total_seconds() > 10:
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
        if isinstance(flavor, six.string_types):
            flavor_id = flavor
        else:
            flavor_id = flavor['id']
        if not nics:
            net_obj = self.cloud.nova.networks.find(label="novanetwork")
            (net, _, addr) = net_obj.dhcp_start.rpartition('.')
            ip = ".".join((net, str(int(addr) + 1)))
            nics = [{
                "net-id": net_obj.id,
                "v4-fixed-ip": ip,
            }]
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
            "metadata": {}},)
        self.objects[server.id] = server
        return server

    def add_floating_ip(self, server_ref, floating_ip, fixed_ip=None):
        floating_ip_addr = {
            "OS-EXT-IPS-MAC:mac_addr": "fa:16:3e:c3:d8:d4",
            "version": 4,
            "addr": floating_ip,
            "OS-EXT-IPS:type": "floating"
        }
        floating_ip_list = self.cloud.nova.floating_ips_bulk.list()
        if hasattr(server_ref, "id"):
            server_id = server_ref.id
        else:
            server_id = server_ref
        server = self.objects[server_id]
        for net in server["addresses"]:
            if not fixed_ip:
                raise NotImplementedError
            for addr in server["addresses"][net]:
                if addr['addr'] == fixed_ip:
                    server['addresses'][net].append(floating_ip_addr)
                    server._info = server
                    for ip in floating_ip_list:
                        if ip.address == floating_ip:
                            ip['instance_uuid'] = ip['instance_id'] = server_id
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

    def create_image(self, server, name):
        image = self.cloud.glance.images.create(name=name,
                                                disk_format="qcow2",
                                                container_format="bare")
        return image.id


class Image(Resource):
    def data(self, id):
        data = AttrDict(self)
        data._resp = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
        return data

    def upload(self, image_id, data):
        if self.cloud.delays:
            time.sleep(random.randint(5, 15))

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
        self.objects[image.id] = image
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
        self.objects[network.id] = network
        return network

    def disassociate(self, network):
        pass


class Flavor(NovaResource):
    def create(self, name, ram, vcpus, disk, **kwargs):
        flavor_id = str(uuid.uuid4())
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
        self.objects[flavor.id] = flavor
        return flavor


class FloatingIP(NovaResource):
    def create(self, pool=None):
        floating_ips = [obj
                        for obj in self._iterate_values()
                        if not obj.project_id]
        if len(floating_ips) < 1:
            raise self.NotFound()
        floating_ip = floating_ips[0]
        floating_ip['ip'] = floating_ip['address']
        floating_ip['project_id'] = self.tenant_id
        floating_ip['instance_id'] = None
        return floating_ip


class FloatingIPPool(NovaResource):
    def create(self, name):
        pool = AttrDict(self, {
            "id": str(uuid.uuid4()),
            "name": name,
        })
        self.objects[pool.id] = pool
        return pool


class FloatingIPBulk(NovaResource):
    def create(self, address, pool=None):
        floating_ip_uuid = uuid.uuid4()
        floating_ip = AttrDict(self, {
            "address": address,
            "id": str(floating_ip_uuid),
            "instance_uuid": None,
            "instance_id": None,
            "project_id": None,
            "pool": pool,
        })
        floating_ip._info = floating_ip
        self.objects[floating_ip.id] = floating_ip
        self.cloud.nova.floating_ip_pools.create(pool)
        return floating_ip

    def delete(self, ip_range):
        for obj_id, obj in self.objects.items():
            if obj.address == ip_range:
                self.objects.pop(obj_id, None)


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
        self.objects[secgroup.id] = secgroup
        return secgroup


class SecGroupRule(Resource):
    def create(self, id, **kwargs):
        rule = AttrDict(self, {
            "id": id,
            "ip_range": {
                "cidr": kwargs["cidr"],
            },
        }, **kwargs)
        self.objects[rule.id] = rule
        return rule


class Hypervisor(NovaResource):
    def list(self):
        return self.objects

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
                   if (host is not None and obj.host == host and
                       binary is not None and obj.binary == binary)]
        return objects

    def disable(self, hostname, binary):
        service = self.find(host=hostname, binary=binary)
        service.status = "disabled"
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
        self.objects[tenant.id] = tenant
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
            "enabled": True,
            "roles": [self.cloud.keystone.roles.find(name="_member_")]
        }, **kwargs)
        self.objects[user.id] = user
        return user


class Role(KeystoneResource):
    def create(self, name):
        role_uuid = uuid.uuid4()
        role = AttrDict(self, {
            "id": str(role_uuid),
            "name": name,
        })
        self.objects[role.id] = role
        return role

    def add_user_role(self, user_id, role_id, tenant):
        for r_id, role in self.objects.iteritems():
            if r_id == role_id:
                break
        for user in self.cloud.keystone.users.list():
            if user.id == user_id:
                if 'roles' in user:
                    user['roles'].append(role)
                else:
                    user['roles'] = [role]
                return
        raise exceptions.NotFound()

    def roles_for_user(self, user_id, **kwargs):
        for user in self.cloud.keystone.users.list():
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
        objects = self.get_named_resource(resource_class, resource_name)
        self.resources[resource_class] = resource = resource_class(self.cloud,
                                                                   objects)
        return resource

    def get_named_resource(self, resource_class, resource_name):
        return self.resources_objects.setdefault(resource_name, {})


class Nova(BaseService):
    servers = Collection(Server)
    flavors = Collection(Flavor)
    networks = Collection(Network)
    floating_ips = Collection(FloatingIP)
    floating_ips_bulk = Collection(FloatingIPBulk)
    floating_ip_pools = Collection(FloatingIPPool)
    security_groups = Collection(SecGroup)
    security_group_rules = Collection(SecGroupRule)
    hypervisors = Collection(Hypervisor)
    services = Collection(Service)

    def schedule_server(self):
        services = self.services._findall(status="enabled",
                                          state="up",
                                          binary="nova-compute")
        service = random.choice(services)
        return service.host

    def get_named_resource(self, resource_class, resource_name):
        if resource_name == "floatingips":
            resource_name = "floatingipbulks"
        return super(Nova, self).get_named_resource(resource_class,
                                                    resource_name)


class Glance(BaseService):
    images = Collection(Image)


class Keystone(BaseService):
    tenants = Collection(Tenant)
    users = Collection(User)
    roles = Collection(Role)
    auth_ref = Collection(AuthRef)


class Cloud(object):
    default_num_hypervisors = 2
    default_delays = False

    def __init__(self, namespace, identity, data=None, fake=None):
        self.namespace = namespace
        self.fake = fake or {}
        self.delays = self.fake.get("delays", self.default_delays)
        self.num_hypervisors = self.fake.get("num_hypervisors",
                                             self.default_num_hypervisors)
        self.populate = self.fake.get("populate", {})
        self.data = data or {}
        self.nova = Nova(self)
        self.keystone = Keystone(self)
        self.glance = Glance(self)
        if isinstance(identity, Identity):
            self.identity = identity
        else:
            self.identity = Identity(**identity)
        if data is None:
            self.initialize_data()

    def ping(self):
        return True

    def initialize_data(self):
        admin_tenant = AttrDict(self.keystone, {
            "name": self.namespace.tenant_name,
            "id": str(uuid.uuid4()),
        }, description="admin")
        admin_role = AttrDict(self.keystone, {
            "name": "admin",
            "id": str(uuid.uuid4()),
        })
        admin_user = AttrDict(self.keystone, {
            "username": self.namespace.username,
            "name": self.namespace.username,
            "id": str(uuid.uuid4()),
            "roles": [admin_role],
            "tenantId": admin_tenant.id,
            "enabled": True,
        })
        member_role = AttrDict(self.keystone, {
            "name": "_member_",
            "id": str(uuid.uuid4()),
        })
        self.data["keystone"]["tenants"] = {admin_tenant.id: admin_tenant}
        self.data["keystone"]["roles"] = {admin_role.id: admin_role,
                                          member_role.id: member_role}
        self.data["keystone"]["users"] = {admin_user.id: admin_user}
        hostname_prefix = "".join(random.choice(string.ascii_uppercase)
                                  for i in (0, 0))
        services = [AttrDict(self.nova, {
            "host": "pumphouse-{}-{}".format(hostname_prefix, i),
            "binary": "nova-compute",
            "state": "up",
            "status": "enabled",
        }) for i in range(self.num_hypervisors)]
        hypervs = [AttrDict(self.nova, {
            "name": s.host,
            "service": s,
        }) for s in services]
        secgroup = AttrDict(self.nova, {
            "name": "default",
            "description": "default",
            "tenant_id": admin_tenant.id,
            "id": str(uuid.uuid4()),
            "rules": "",
        })
        network = AttrDict(self.nova, {
            "bridge": "br100",
            "vpn_public_port": None,
            "dhcp_start": "10.10.0.2",
            "bridge_interface": "eth0",
            "updated_at": str(datetime.datetime.now()),
            "id": str(uuid.uuid4()),
            "cidr_v6": None,
            "deleted_at": None,
            "gateway": "10.10.0.1",
            "rxtx_base": None,
            "priority": None,
            "project_id": None,
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
            "host": None,
            "gateway_v6": None,
            "netmask_v6": None,
            "dns1": "8.8.4.4",
            "label": "novanetwork",
        })
        self.data["nova"]["services"] = services
        self.data["nova"]["hypervisors"] = hypervs
        self.data["nova"]["secgroups"] = {secgroup.id: secgroup}
        self.data["nova"]["networks"] = {network.id: network}

    def get_service(self, service_name):
        return self.data.setdefault(service_name, {})

    def restrict(self, **kwargs):
        namespace = self.namespace.restrict(**kwargs)
        return self.__class__(namespace, self.identity, data=self.data)

    @classmethod
    def from_dict(cls, endpoint, identity, **kwargs):
        namespace = pump_cloud.Namespace(
            username=endpoint["username"],
            password=endpoint["password"],
            tenant_name=endpoint["tenant_name"],
            auth_url=endpoint["auth_url"],
        )
        cloud = cls(namespace, identity, **kwargs)
        return cloud

    def __repr__(self):
        return "<Cloud(namespace={!r})>".format(self.namespace)


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


class Service(base.Service):
    def reset(self, events, cloud):
        cloud.delays, delays = False, cloud.delays
        super(Service, self).reset(events, cloud)
        cloud.delays = delays
        return cloud
