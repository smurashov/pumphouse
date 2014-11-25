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

import collections
import functools
import itertools
import random
import tempfile
import urllib

import netaddr
from novaclient import exceptions as nova_excs

from pumphouse import events
from pumphouse.tasks import base
from pumphouse import utils


TEST_IMAGE_URL = ("http://download.cirros-cloud.net/0.3.2/"
                  "cirros-0.3.2-x86_64-disk.img")
TEST_RESOURCE_PREFIX = "pumphouse-"


def is_prefixed(string):
    return string.startswith(TEST_RESOURCE_PREFIX)


def filter_prefixed(lst, dict_=False, key="name"):
    return [(dict(e) if dict_ else e.to_dict())
            for e in lst if is_prefixed(getattr(e, key))]


def make_kwargs(**kwargs):
    return {k: v for k, v in kwargs.iteritems() if v is not None}


class EventTask(base.UnboundTask):
    def __init__(self, *args, **kwargs):
        self.pre_event = kwargs.pop("pre_event", None)
        self.post_event = kwargs.pop("post_event", None)
        super(EventTask, self).__init__(*args, **kwargs)

    def wrapper(self, fn):
        @functools.wraps(fn)
        def inner(resource):
            if self.pre_event is None:
                resource.pre_event(self.name)
            else:
                self.pre_event(resource)
            res = fn(resource)
            if self.post_event is None:
                resource.post_event(self.name)
            else:
                self.post_event(resource)
            return res
        return inner

task = EventTask


class EventResource(base.Resource):
    class __metaclass__(base.Resource.__metaclass__):
        def __new__(mcs, name, bases, cls_vars):
            if "events_type" not in cls_vars:
                cls_vars["events_type"] = name.lower()
            return base.Resource.__metaclass__.__new__(mcs, name, bases,
                                                       cls_vars)

    event_id_key = "id"

    def event_id(self):
        return self.data[self.event_id_key]

    def event_data(self):
        return self.data

    def pre_event(self, name):
        pass

    def post_event(self, name):
        event = {
            "id": self.event_id(),
            "type": self.events_type,
            "cloud": self.env.cloud.name,
            "action": None,
            "progress": None,
            "data": self.event_data(),
        }
        if name == "create":
            events.emit(name, event, namespace="/events")
        elif name == "delete":
            event["data"] = None
            events.emit(name, event, namespace="/events")
        else:
            events.emit("update", event, namespace="/events")


class Tenant(EventResource):
    data_id_key = "name"

    @task
    def create(self):
        tenant = self.env.cloud.keystone.tenants.create(
            self.data["name"],
            **make_kwargs(
                description=self.data.get("description"),
                enabled=self.data.get("enabled"),
            )
        )
        our_user_id = self.env.cloud.keystone.auth_ref.user_id
        all_roles = self.env.cloud.keystone.roles.list()
        admin_role = [r for r in all_roles if r.name == "admin"][0]
        self.env.cloud.keystone.tenants.add_user(
            tenant.id,
            our_user_id,
            admin_role.id,
        )
        self.data = tenant.to_dict()

    @task(before=[create])
    def delete(self):
        self.env.cloud.keystone.tenants.delete(self.data["id"])


class Role(EventResource):
    data_id_key = "name"

    @task
    def create(self):
        self.data = self.env.cloud.keystone.role.create(
            name=self.data["name"],
        ).to_dict()

    @task(before=[create])
    def delete(self):
        self.env.cloud.keystone.roles.delete(self.data["id"])


class User(EventResource):
    data_id_key = "name"

    @Tenant()
    def tenant(self):
        return self.data["tenant"]

    @task(requires=[tenant.create])
    def create(self):
        self.data = self.env.cloud.keystone.users.create(
            name=self.data["name"],
            password="default",
            tenant_id=self.tenant["id"],
        ).to_dict()

    @task(before=[create])
    def delete(self):
        self.env.cloud.keystone.users.delete(self.data["id"])


class Flavor(EventResource):
    data_id_key = "name"

    @task
    def create(self):
        swap = self.data.get("swap")
        if swap == '':
            swap = None
        elif swap is not None:
            swap = int(swap)
        self.data = self.env.cloud.nova.flavors.create(
            self.data["name"],
            self.data["ram"],
            self.data["vcpus"],
            self.data["disk"],
            **make_kwargs(
                flavorid=self.data.get("id"),
                ephemeral=self.data.get("ephemeral"),
                swap=swap,
                rxtx_factor=self.data.get("rxtx_factor"),
                is_public=self.data.get("is_public"),
            )
        ).to_dict()

    @task(before=[create])
    def delete(self):
        self.env.cloud.nova.flavors.delete(self.data["id"])


class SecurityGroup(EventResource):
    events_type = "secgroup"

    @classmethod
    def get_id_for(cls, data):
        return (data["tenant"]["name"], data["name"])

    @Tenant()
    def tenant(self):
        return self.data["tenant"]

    @task(requires=[tenant.create])
    def create(self):
        cloud = self.env.cloud.restrict(
            tenant_name=self.tenant["name"],
        )
        sg_name = self.data["name"]
        if sg_name != "default":
            sg = cloud.nova.security_groups.create(name=sg_name)
        else:
            sg = cloud.nova.security_groups.find(name=sg_name)
        for rule in self.data["rules"]:
            cloud.nova.security_group_rules.create(sg.id, **rule)
        self.data = cloud.nova.security_groups.get(sg.id).to_dict()

    @task(before=[create, tenant.delete])
    def delete(self):
        if self.data["name"] != "default":
            cloud.nova.security_groups.delete(self.data["id"])
        else:
            for rule in self.data["rules"]:
                self.env.cloud.nova.security_group_rules.delete(rule["id"])


class CachedImage(EventResource):
    data_id_key = "url"

    def pre_event(self, name):
        pass

    def post_event(self, name):
        pass

    @task
    def cache(self):
        f = tempfile.NamedTemporaryFile(delete=True)
        img = urllib.urlopen(self.data["url"])
        # Based on urllib.URLOpener.retrieve
        try:
            headers = img.info()
            bs = 1024 * 8
            size = -1
            read = 0
            if "content-length" in headers:
                size = int(headers["Content-Length"])
            while 1:
                block = img.read(bs)
                if block == "":
                    break
                read += len(block)
                f.write(block)
        finally:
            img.close()
        if size >= 0 and read < size:
            raise urllib.ContentTooShortError(
                "retrieval incomplete: got only %i out of %i bytes" % (
                    read, size), (None, headers))

        f.flush()
        self.data = {"url": self.data["url"], "file": f}


class Image(EventResource):
    @CachedImage()
    def cached_image(self):
        return {"url": self.data["url"]}

    @task(requires=[cached_image.cache])
    def create(self):
        image = self.data.copy()
        image.pop("url")
        image.setdefault("visibility", "public")
        image = self.env.cloud.glance.images.create(**image)
        self.data = dict(image)

    @task(requires=[create])
    def upload(self):
        # upload starts here
        with open(self.cached_image["file"].name, 'rb') as f:
            self.env.cloud.glance.images.upload(self.data["id"], f)
        image = self.env.cloud.glance.images.get(self.data["id"])
        self.data = dict(image)

    @task(before=[create])
    def delete(self):
        self.env.cloud.glance.images.delete(self.data["id"])


class Subnet(base.Plugin):
    plugin_key = "network"
    default = "nova"


@Subnet.register("nova")
class NovaSubnet(EventResource):
    data_id_key = "cidr"
    event_id_key = "cidr"

    create = task(name="create")
    delete = task(name="delete", before=[create])


class Network(base.Plugin):
    plugin_key = "network"
    default = "nova"


@Network.register("nova")
class NovaNetwork(EventResource):
    data_id_key = "label"
    events_type = "network"

    @Tenant()
    def tenant(self):
        return self.data["tenant"]

    @Subnet()
    def subnet(self):
        cidr = self.data["cidr"]
        if isinstance(cidr, list):
            cidr = str(list(netaddr.IPSet(cidr).iter_cidrs())[0])
        return {"cidr": cidr}

    @task(requires=[tenant.create, subnet.create])
    def create(self):
        self.data = self.env.cloud.nova.networks.create(
            label=self.data["label"],
            cidr=self.data["cidr"],
            project_id=self.tenant["id"],
        ).to_dict()

    @task(before=[create], includes=[subnet.delete])
    def delete(self):
        self.env.cloud.nova.networks.disassociate(self.data["id"])
        self.env.cloud.nova.networks.delete(self.data["id"])


class FloatingIP(base.Plugin):
    plugin_key = "network"
    default = "nova"


@FloatingIP.register("nova")
class NovaFloatingIP(EventResource):
    data_id_key = "address"
    event_id_key = "address"
    events_type = "floating_ip"

    def event_data(self):
        data = self.data.copy()
        data["name"] = data["address"]
        return data

    @task
    def create(self):
        self.env.cloud.nova.floating_ips_bulk.create(
            self.data["address"],
            pool=self.data["pool"],
        )

    @task(requires=[create])
    def associate(self):
        self.env.cloud.nova.servers.add_floating_ip(
            self.data["server"]["id"],
            self.data["address"],
            self.data["fixed_ip"]["address"],
        )

    @task
    def disassociate(self):
        if self.data.get("server"):
            self.env.cloud.nova.servers.remove_floating_ip(
                self.data["server"]["id"],
                self.data["address"],
            )

    @task(before=[create], requires=[disassociate])
    def delete(self):
        self.env.cloud.nova.floating_ips_bulk.delete(
            self.data["address"],
        )


class NovaFixedIP(EventResource):
    @classmethod
    def get_id_for(cls, data):
        return (
            NovaNetwork.get_id_for(data["network"]),
            data["address"],
        )

    def event_id(self):
        return "_".join(self.get_id_for(self.data))

    @NovaNetwork()
    def network(self):
        return self.data["network"]

    @task(requires=[network.create])
    def create(self):
        self.data = {
            "network": self.network,
            "address": self.data["address"],
        }

    delete = task(name="delete", before=[network.delete])


class Nic(base.Plugin):
    plugin_key = "network"
    default = "nova"


@Nic.register("nova")
class NovaNic(EventResource):
    @classmethod
    def get_id_for(cls, data):
        return NovaFixedIP.get_id_for(data["fixed_ip"])

    def event_id(self):
        return "_".join(self.get_id_for(self.data))

    @NovaFixedIP()
    def fixed_ip(self):
        return self.data["fixed_ip"]

    @task(requires=[fixed_ip.create])
    def create(self):
        self.data = {
            "fixed_ip": self.data["fixed_ip"],
            "nic": {
                "net-id": self.fixed_ip["network"]["id"],
                "v4-fixed-ip": self.fixed_ip["address"],
            },
        }

    delete = task(name="delete", includes=[fixed_ip.delete])


class Server(EventResource):
    def event_data(self):
        data = self.data.copy()
        data["image_id"] = data["image"]["id"]
        return data

    @Tenant()
    def tenant(self):
        # FIXME(yorik-sar): Use just id here and bind it to real data later
        return self.data["tenant"]

    @User()
    def user(self):
        return self.data["user"]

    @Image()
    def image(self):
        return self.data["image"]

    @Flavor()
    def flavor(self):
        return self.data["flavor"]

    @base.Collection(FloatingIP)
    def floating_ips(self):
        for floating_ip in self.data["floating_ips"]:
            floating_ip = floating_ip.copy()
            floating_ip["server"] = self.data
            yield floating_ip

    @base.Collection(Nic)
    def nics(self):
        for fixed_ip in self.data["fixed_ips"]:
            yield {
                "fixed_ip": fixed_ip,
            }

    @task(requires=[image.upload, tenant.create, flavor.create, user.create,
                    nics.each().create, floating_ips.each().create],
          includes=[floating_ips.each().associate])
    def create(self):
        cloud = self.env.cloud.restrict(
            username=self.user["name"],
            password="default",
            tenant_name=self.tenant["name"],
        )
        servers = cloud.nova.servers
        server = servers.create(
            self.data["name"],
            self.image["id"],
            self.flavor["id"],
            nics=[nic["nic"] for nic in self.nics],
        )
        server = utils.wait_for(server.id, servers.get, value="ACTIVE")
        self.data = server = server.to_dict()
        for floating_ip in self.floating_ips:
            floating_ip["server"] = server

    @task(before=[tenant.delete],
          requires=[floating_ips.each().disassociate],
          includes=[nics.each().delete])
    def delete(self):
        self.env.cloud.nova.servers.delete(self.data["id"])
        utils.wait_for(self.data["id"], self.env.cloud.nova.servers.get,
                       stop_excs=(nova_excs.NotFound,))


class CleanupWorkload(EventResource):
    @base.Collection(Tenant)
    def tenants(self):
        tenants = self.env.cloud.keystone.tenants.list()
        return filter_prefixed(tenants)

    @base.Collection(Role)
    def roles(self):
        roles = self.env.cloud.keystone.roles.list()
        return filter_prefixed(roles)

    @base.Collection(User)
    def users(self):
        users = self.env.cloud.keystone.users.list()
        return filter_prefixed(users)

    @base.Collection(Server)
    def servers(self):
        servers = self.env.cloud.nova.servers.list(
            search_opts={"all_tenants": 1})
        servers = filter_prefixed(servers)
        # FIXME(yorik-sar): workaroud for missing resource lookup by id
        tenants = {tenant["id"]: tenant for tenant in self.tenants}
        floating_ips = collections.defaultdict(list)
        for floating_ip in self.floating_ips:
            server_id = floating_ip["instance_uuid"]
            if server_id:
                floating_ips[server_id].append(floating_ip)
        networks = {network["label"]: network for network in self.networks}
        for server in servers:
            server["tenant"] = tenants[server["tenant_id"]]
            server["floating_ips"] = floating_ips[server["id"]]
            fixed_ips = server["fixed_ips"] = []
            for label, addrs in server["addresses"].iteritems():
                if label not in networks:
                    continue
                for addr in addrs:
                    if addr["OS-EXT-IPS:type"] == "fixed":
                        fixed_ips.append({
                            "address": addr["addr"],
                            "network": networks[label],
                        })
        return servers

    @base.Collection(Flavor)
    def flavors(self):
        return filter_prefixed(self.env.cloud.nova.flavors.list())

    @base.Collection(SecurityGroup)
    def security_groups(self):
        tenants = {tenant["id"]: tenant for tenant in self.tenants}
        for sg in self.env.cloud.nova.security_groups.list():
            if sg.tenant_id in tenants:
                sg = sg.to_dict()
                sg["tenant"] = tenants[sg["tenant_id"]]
                yield sg

    @base.Collection(Network)
    def networks(self):
        networks = self.env.cloud.nova.networks.list()
        return filter_prefixed(networks, key="label")

    @base.Collection(FloatingIP)
    def floating_ips(self):
        floating_ips = self.env.cloud.nova.floating_ips_bulk.list()
        return [f.to_dict() for f in floating_ips]

    @base.Collection(Image)
    def images(self):
        return filter_prefixed(self.env.cloud.glance.images.list(), dict_=True)

    delete = base.task(name="delete", requires=[
        tenants.each().delete,
        roles.each().delete,
        users.each().delete,
        servers.each().delete,
        flavors.each().delete,
        security_groups.each().delete,
        networks.each().delete,
        floating_ips.each().delete,
        images.each().delete,
    ])


class SetupWorkload(EventResource):
    @base.Collection(Tenant)
    def tenants(self):
        tenants = self.data["workloads"].get("tenants")
        if tenants is not None:
            for tenant in tenants:
                yield tenant
            return
        for i in xrange(self.data["populate"].get("num_tenants", 2)):
            tenant_ref = str(random.randint(1, 0x7fffffff))
            yield {
                "name": "{}-{}".format(TEST_RESOURCE_PREFIX, tenant_ref),
                "description": "pumphouse test tenant {}".format(tenant_ref),
                "username": "{}-user-{}"
                            .format(TEST_RESOURCE_PREFIX, tenant_ref),
            }

    @base.Collection(User)
    def users(self):
        users = self.data["workloads"].get("users")
        if users is not None:
            for user in users:
                yield user
            return
        for tenant in self.tenants:
            yield {
                "name": tenant["username"],
                "tenant": tenant,
            }

    @base.Collection(Image)
    def images(self):
        images = self.data["workloads"].get("images")
        if images is not None:
            return images
        return [{
            "name": "{}-image".format(TEST_RESOURCE_PREFIX),
            "disk_format": "qcow2",
            "container_format": "bare",
            "visibility": "public",
            "url": TEST_IMAGE_URL,
        }]

    @base.Collection(Flavor)
    def flavors(self):
        flavors = self.data["workloads"].get("flavors")
        if flavors is not None:
            return flavors
        return [{
            "name": "{}-flavor".format(TEST_RESOURCE_PREFIX),
            "ram": 1024,
            "vcpus": 1,
            "disk": 5,
        }]

    @base.Collection(SecurityGroup)
    def security_groups(self):
        for tenant in self.tenants:
            yield {
                "name": "default",
                "rules": [
                    {
                        "ip_protocol": "ICMP",
                        "from_port": "-1",
                        "to_port": "-1",
                        "cidr": "0.0.0.0/0",
                    },
                    {
                        "ip_protocol": "TCP",
                        "from_port": "80",
                        "to_port": "80",
                        "cidr": "0.0.0.0/0",
                    },
                ],
                "tenant": tenant,
            }

    @base.Collection(Network)
    def networks(self):
        networks = self.data["workloads"].get("networks")
        if networks is not None:
            for network in networks:
                yield network
            return
        counter = itertools.count(1)
        for tenant in self.tenants:
            yield {
                "label": "{}-network-{}".format(
                    TEST_RESOURCE_PREFIX,
                    tenant["name"].rsplit("-", 1)[-1],
                ),
                "cidr": "10.42.{}.0/24".format(counter.next()),
                "tenant": tenant,
            }

    @base.Collection(FloatingIP)
    def floating_ips(self):
        floating_ips = self.data["workloads"].get("floating_ips")
        if floating_ips is not None:
            for floating_ip in floating_ips:
                yield floating_ip
            return
        counter = itertools.count(136)
        num_servers = self.data["populate"].get("num_servers", 2)
        for tenant in self.tenants:
            try:
                num = len(tenant["servers"])
            except KeyError:
                num = num_servers
            for i in xrange(num):
                floating_ip = {
                    "address": "127.16.0.{}".format(counter.next()),
                    "pool": TEST_RESOURCE_PREFIX + "-pool",
                }
                yield floating_ip

    @base.Collection(Server)
    def servers(self):
        num_servers = self.data["populate"].get("num_servers", 2)

        def get_base_servers(tenant):
            if "servers" in tenant:
                for server in tenant["servers"]:
                    yield server
            else:
                for i in xrange(num_servers):
                    server_ref = str(random.randint(1, 0x7fffffff))
                    image = random.choice(self.images)
                    flavor = random.choice(self.flavors)
                    yield {
                        "name": "{}-{}".format(TEST_RESOURCE_PREFIX,
                                               server_ref),
                        "image": image,
                        "flavor": flavor,
                    }

        tenant_nets = {}
        floating_ips = iter(self.floating_ips)
        for network in self.networks:
            addrs = iter(netaddr.IPNetwork(network["cidr"]).iter_hosts())
            for i in xrange(42):
                next(addrs)
            nets = tenant_nets.setdefault(network["tenant"]["name"], [])
            nets.append((network, addrs))
        for tenant in self.tenants:
            for server in get_base_servers(tenant):
                server.update({
                    "tenant": tenant,
                    "user": {
                        "name": tenant["username"],
                        "tenant": tenant,
                    },
                    "floating_ips": [],
                    "fixed_ips": [],
                })
                for network, addrs in tenant_nets[tenant["name"]]:
                    fixed_ip = {
                        "address": str(next(addrs)),
                        "network": network,
                    }
                    server["fixed_ips"].append(fixed_ip)
                    floating_ip = next(floating_ips)
                    floating_ip["fixed_ip"] = fixed_ip
                    server["floating_ips"].append(floating_ip)
                yield server

    create = base.task(name="create", requires=[
        tenants.each().create,
        users.each().create,
        images.each().upload,
        flavors.each().create,
        security_groups.each().create,
        networks.each().create,
        floating_ips.each().create,
        servers.each().create,
    ])


Environment = collections.namedtuple("Environment", ["cloud", "plugins"])

if __name__ == "__main__":
    import logging

    from pumphouse import cloud as p_cloud
    from pumphouse.cmds import api

    logging.basicConfig(level=logging.DEBUG)
    config = api.get_parser().parse_args().config
    source_config = config["CLOUDS"]["source"]
    cloud = p_cloud.Cloud.from_dict("src", source_config["endpoint"], None)
    env = Environment(cloud)
    runner = base.TaskflowRunner(env)
    cleanup_workload = runner.get_resource(CleanupWorkload, {"id": "src"})
    runner.add(cleanup_workload.delete)
    runner.run()
    runner = base.TaskflowRunner(env)
    setup_workload = runner.get_resource(SetupWorkload, {
        "id": "src",
        "populate": source_config.get("populate"),
        "workloads": source_config.get("workloads"),
    })
    runner.add(setup_workload.create)
    runner.run()
