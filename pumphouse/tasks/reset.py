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

from __future__ import division

import collections
import functools
import itertools
import logging
import random
import time
import tempfile
import urllib

import netaddr
from neutronclient.common import exceptions as neutron_excs
from novaclient import exceptions as nova_excs

from pumphouse import events
from pumphouse import exceptions
from pumphouse.tasks import base
from pumphouse import utils

LOG = logging.getLogger(__name__)

TEST_IMAGE_URL = ("http://download.cirros-cloud.net/0.3.2/"
                  "cirros-0.3.2-x86_64-disk.img")
TEST_RESOURCE_PREFIX = "pumphouse-"


def is_prefixed(string):
    return string.startswith(TEST_RESOURCE_PREFIX)


def filter_prefixed(lst, convert_fn=None, key="name"):
    if convert_fn is None:
        items = (e.to_dict() for e in lst)
    else:
        items = itertools.imap(convert_fn, lst)
    return [e for e in items if is_prefixed(e[key])]


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
            if not resource.mute_events:
                if self.pre_event is None:
                    resource.pre_event(self.name)
                else:
                    self.pre_event(resource)
            res = fn(resource)
            if not resource.mute_events:
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

    mute_events = False
    event_id_key = "id"

    def event_id(self):
        return self.data[self.event_id_key]

    def event_data(self):
        return self.data

    def pre_event(self, name):
        pass

    def get_base_event_body(self):
        return {
            "id": self.event_id(),
            "type": self.events_type,
            "cloud": self.env.cloud.name,
            "action": None,
            "progress": None,
            "data": self.event_data(),
        }

    def post_event(self, name):
        event = self.get_base_event_body()
        if name == "create":
            events.emit(name, event, namespace="/events")
        elif name == "delete":
            event["data"] = None
            events.emit(name, event, namespace="/events")
        else:
            events.emit("update", event, namespace="/events")

    def progress_event(self, progress):
        event = self.get_base_event_body()
        event["progress"] = int(progress)
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


class FileReadProgress(object):
    def __init__(self, f, size, resource, action="Reading"):
        self.f = f
        self.size = size
        self.resource = resource
        self.action = action
        self.reported = self.read_size = 0
        self.reported_time = time.time()

    def read(self, sz):
        res = self.f.read(sz)
        self.read_size += len(res)
        now = time.time()
        progress_since = (self.read_size - self.reported) / self.size
        if progress_since > 0.1 or\
                (now - self.reported_time) > 1 and progress_since > 0.01:
            progress = (self.read_size / self.size) * 100
            if not self.resource.mute_events:
                self.resource.progress_event(progress)
            LOG.debug("%s %s progress %3.2f%%", self.action, self.resource,
                      progress)
            self.reported = self.read_size
            self.reported_time = now
        return res


class CachedImage(EventResource):
    data_id_key = "url"
    mute_events = True

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
                p_img = FileReadProgress(img, size, self, "Caching")
            else:
                p_img = img
            while 1:
                block = p_img.read(bs)
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
        self.data = {"url": self.data["url"], "file": f, "size": read}


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
            f = FileReadProgress(f, self.cached_image["size"], self,
                                 "Uploading")
            self.env.cloud.glance.images.upload(self.data["id"], f)
        image = self.env.cloud.glance.images.get(self.data["id"])
        self.data = dict(image)

    @task(before=[create])
    def delete(self):
        self.env.cloud.glance.images.delete(self.data["id"])


class Subnet(base.Plugin):
    plugin_key = "network"
    default = "nova"


class Network(base.Plugin):
    plugin_key = "network"
    default = "nova"


class FloatingIP(base.Plugin):
    plugin_key = "network"
    default = "nova"


class Nic(base.Plugin):
    plugin_key = "network"
    default = "nova"


@Subnet.register("nova")
class NovaSubnet(EventResource):
    data_id_key = "cidr"
    event_id_key = "cidr"
    events_type = "subnet"

    create = task()
    delete = task(before=[create])


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


@FloatingIP.register("nova")
class NovaFloatingIP(EventResource):
    data_id_key = "address"
    event_id_key = "address"
    events_type = "floating_ip"

    def event_data(self):
        return {
            "name": self.data["address"],
            "address": self.data["address"],
            "interface": self.data.get("interface"),
            "server_id": self.data.get("server", {}).get("id"),
            "tenant_id": self.data.get("project_id"),
        }

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
            self.data = dict(self.data)
            del self.data["server"]

    @task(before=[create], requires=[disassociate])
    def delete(self):
        self.env.cloud.nova.floating_ips_bulk.delete(
            self.data["address"],
        )


class NovaFixedIP(EventResource):
    mute_events = True

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

    delete = task(before=[network.delete])


@Nic.register("nova")
class NovaNic(EventResource):
    mute_events = True

    @classmethod
    def get_id_for(cls, data):
        return NovaFixedIP.get_id_for(data["fixed_ip"])

    def event_id(self):
        return "_".join(self.get_id_for(self.data))

    def event_data(self):
        return {
            "address": self.fixed_ip["address"],
        }

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

    delete = task(includes=[fixed_ip.delete])


@Subnet.register("neutron")
class NeutronSubnet(EventResource):
    @classmethod
    def get_id_for(cls, data):
        cidr = data["cidr"]
        if cidr is None:
            cidr = ""
        return (NeutronNetwork.get_id_for(data["network"]), cidr)

    events_type = "subnet"

    def event_id(self):
        return "_".join(self.get_id_for(self.data))

    def event_data(self):
        return {
            "cidr": self.data.get("cidr"),
            "network_id": self.data.get("network_id"),
        }

    @task
    def create(self):
        subnet = self.env.cloud.neutron.create_subnet({"subnet": {
            "network_id": self.data["network"]["id"],
            "cidr": self.data["cidr"],
            "ip_version": 4,
        }})["subnet"]
        self.data = dict(
            subnet,
            network=self.data["network"],
        )
        self.env.cloud.neutron.add_interface_router(
            self.data["network"]["router"]["id"],
            {"subnet_id": subnet["id"]},
        )

    @task(before=[create])
    def delete(self):
        if self.data["cidr"] is not None:
            self.env.cloud.neutron.delete_subnet(self.data["id"])


@Network.register("neutron")
class NeutronNetwork(EventResource):
    events_type = "network"

    @classmethod
    def get_id_for(cls, data):
        try:
            return data["label"]
        except KeyError:
            return data["name"]

    def event_data(self):
        return {
            "id": self.data.get("id"),
            "name": self.data.get("name"),
            "status": self.data.get("status"),
            "tenant_id": self.data.get("tenant_id"),
        }

    @Tenant()
    def tenant(self):
        return self.data["tenant"]

    @Subnet()
    def subnet(self):
        try:
            # FIXME(yorik-sar): multiple subnets support
            subnet_id = self.data["subnets"][0]
        except KeyError:
            subnet = {"cidr": self.data["cidr"]}
        except IndexError:
            subnet = {"cidr": None}
        else:
            subnet = self.env.cloud.neutron.show_subnet(subnet_id)["subnet"]
        subnet["network"] = self.data
        return subnet

    @task(requires=[subnet.create])
    def save_subnet(self):
        self.data = dict(
            self.data,
            subnets=[self.subnet["id"]],
        )

    @task(requires=[tenant.create], includes=[subnet.create, save_subnet])
    def create(self):
        cloud = self.env.cloud.restrict(
            tenant_name=self.tenant["name"],
        )
        network = cloud.neutron.create_network({"network": {
            "name": self.data["label"],
            "tenant_id": self.tenant["id"],
        }})["network"]
        network["tenant"] = self.data["tenant"]
        public_net = self.env.cloud.neutron.list_networks(**{
            "router:external": True,
        })["networks"][0]
        network["router"] = cloud.neutron.create_router({"router": {
            "external_gateway_info": {"network_id": public_net["id"]},
        }})["router"]
        self.data = network
        self.subnet["network"] = network

    @task(before=[subnet.delete])
    def clear_ports(self):
        neutron = self.env.cloud.neutron
        for port in neutron.list_ports(network_id=self.data["id"])["ports"]:
            if port["device_owner"] == "network:router_interface":
                neutron.remove_interface_router(
                    port["device_id"],
                    {"subnet_id": port["fixed_ips"][0]["subnet_id"]},
                )
            else:
                neutron.delete_port(port["id"])

    @task(before=[create], requires=[clear_ports, subnet.delete])
    def delete(self):
        self.env.cloud.neutron.delete_network(self.data["id"])


class NeutronPort(EventResource):
    @classmethod
    def get_id_for(cls, data):
        return (
            NeutronNetwork.get_id_for(data["network"]),
            data["address"],
        )

    events_type = "port"

    def event_id(self):
        return "_".join(self.get_id_for(self.data))

    def event_data(self):
        return {
            "address": self.data.get("address"),
            "network_id": self.data.get("network_id"),
        }

    @NeutronNetwork()
    def network(self):
        return self.data["network"]

    @task(requires=[network.create])
    def create(self):
        cloud = self.env.cloud.restrict(
            tenant_name=self.network["tenant"]["name"],
        )
        port = cloud.neutron.create_port(body={"port": {
            "network_id": self.network["id"],
            "fixed_ips": [{
                # FIXME(yorik-sar): select proper subnet
                "subnet_id": self.network["subnets"][0],
                "address": self.data["address"],
            }],
        }})["port"]
        self.data = dict(
            port,
            network=self.data["network"],
            address=self.data["address"],
        )

    @task(before=[network.delete, create])
    def delete(self):
        try:
            self.env.cloud.neutron.delete_port(self.data["id"])
        # KeyError can be raised if we came here through Server
        except (neutron_excs.PortNotFoundClient, KeyError):
            pass


@FloatingIP.register("neutron")
class NeutronFloatingIP(EventResource):
    events_type = "floating_ip"

    @classmethod
    def get_id_for(self, data):
        try:
            return data["address"]
        except KeyError:
            return data["floating_ip_address"]

    def event_id(self):
        return self.get_id_for(self.data)

    def event_data(self):
        data = self.data.copy()
        try:
            data["name"] = data["address"]
        except KeyError:
            data["name"] = data["floating_ip_address"]
        return data

    @NeutronNetwork()
    def public_network(self):
        nets = self.env.cloud.neutron.list_networks(**{
            "router:external": True,
        })
        return nets["networks"][0]

    @NeutronPort()
    def port(self):
        return self.data["fixed_ip"]

    @Tenant()
    def tenant(self):
        return self.data["fixed_ip"]["network"]["tenant"]

    @task(requires=[tenant.create])
    def create(self):
        cloud = self.env.cloud.restrict(tenant_name=self.tenant["name"])
        self.data = cloud.neutron.create_floatingip({"floatingip": {
            "floating_network_id": self.public_network["id"],
        }})["floatingip"]

    @task(requires=[create, port.create])
    def associate(self):
        self.data = self.env.cloud.neutron.update_floatingip(
            self.data["id"],
            {
                "floatingip": {
                    "port_id": self.port["id"],
                }
            },
        )["floatingip"]

    @task(before=[port.delete])
    def disassociate(self):
        try:
            self.data = self.env.cloud.neutron.update_floatingip(
                self.data["id"],
                {
                    "floatingip": {
                        "port_id": None,
                    }
                },
            )["floatingip"]
        except neutron_excs.PortNotFoundClient:
            pass

    @task(before=[create], requires=[disassociate])
    def delete(self):
        self.env.cloud.neutron.delete_floatingip(self.data["id"])


@Nic.register("neutron")
class NeutronNic(EventResource):
    mute_events = True

    @classmethod
    def get_id_for(cls, data):
        return NeutronPort.get_id_for(data["fixed_ip"])

    @NeutronPort()
    def port(self):
        return self.data["fixed_ip"]

    @task(requires=[port.create])
    def create(self):
        self.data = {
            "fixed_ip": self.data["fixed_ip"],
            "nic": {
                "port-id": self.port["id"],
            },
        }

    delete = task(includes=[port.delete])


class Volume(EventResource):
    def event_data(self):
        attachments = [attachment["server_id"]
                       for attachment in self.data["attachments"]]
        return {
            "id": self.data["id"],
            "status": self.data["status"],
            "name": self.data["display_name"],
            "tenant_id": self.data.get("os-vol-tenant-attr:tenant_id"),
            "host_id": self.data.get("os-vol-host-attr:host"),
            "size": self.data["size"],
            "type": self.data.get("volume_type"),
            "server_ids": attachments,
        }

    @Tenant()
    def tenant(self):
        return self.data["tenant"]

    @task(requires=[tenant.create])
    def create(self):
        cloud = self.env.cloud.restrict(
            tenant_name=self.tenant["name"],
        )
        volume = cloud.cinder.volumes.create(
            self.data["size"],
            display_name=self.data["display_name"],
        )
        volume = utils.wait_for(volume.id, self.env.cloud.cinder.volumes.get,
                                value="available")
        self.data = dict(volume._info,
                         **make_kwargs(
                             server=self.data.get("server"),
                         ))

    @task(requires=[create])
    def attach(self):
        if self.data.get("server"):
            device = None
            self.env.cloud.nova.volumes.create_server_volume(
                self.data["server"]["id"], self.data["id"], device)
            volume = utils.wait_for(self.data["id"],
                                    self.env.cloud.cinder.volumes.get,
                                    value="in-use")
            self.data = volume._info

    @task
    def detach(self):
        for attachment in self.data["attachments"]:
            server_id = attachment["server_id"]
            self.env.cloud.nova.volumes.delete_server_volume(server_id,
                                                             self.data["id"])
        if self.data["attachments"]:
            volume = utils.wait_for(self.data["id"],
                                    self.env.cloud.cinder.volumes.get,
                                    value="available")
            self.data = volume._info

    @task(before=[create], requires=[detach])
    def delete(self):
        self.env.cloud.cinder.volumes.delete(self.data["id"])


class Server(EventResource):
    def event_data(self):
        return {
            "id": self.data["id"],
            "name": self.data["name"],
            "status": self.data["status"],
            "tenant_id": self.data["tenant_id"],
            "image_id": self.data["image"]["id"],
            "host_id": self.data.get("OS-EXT-SRV-ATTR:hypervisor_hostname"),
        }

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

    @base.Collection(Volume)
    def volumes(self):
        if "status" in self.data and self.data["status"] != "active":
            return []
        return self.data.get("os-extended-volumes:volumes_attached")

    mute_events = True  # Events will be handled manualy here

    @task(requires=[image.upload, tenant.create, flavor.create, user.create,
                    nics.each().create, floating_ips.each().create],
          includes=[floating_ips.each().associate, volumes.each().attach])
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

        def do_get(id_, created=[]):
            res = servers.get(id_)
            self.data = res.to_dict()
            if not created:
                self.post_event("create")
                created.append(True)
            else:
                self.post_event("update")
            return res

        server = utils.wait_for(server.id, do_get, value="ACTIVE").to_dict()
        for floating_ip in self.floating_ips:
            floating_ip["server"] = server
        for volume in self.volumes:
            volume["server"] = server

    @task(before=[tenant.delete],
          requires=[floating_ips.each().disassociate, volumes.each().detach],
          includes=[nics.each().delete])
    def delete(self):
        self.env.cloud.nova.servers.delete(self.data["id"])
        utils.wait_for(self.data["id"], self.env.cloud.nova.servers.get,
                       stop_excs=(nova_excs.NotFound,))
        self.post_event("delete")


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
        # NOTE(yorik-sar): Neutron does this through ports
        if self.env.plugins["network"] == "nova":
            for floating_ip in self.floating_ips:
                server_id = floating_ip["instance_uuid"]
                if server_id:
                    floating_ips[server_id].append(floating_ip)
        elif self.env.plugins["network"] == "neutron":
            for floating_ip in self.floating_ips:
                server_id = floating_ip["fixed_ip"].get("device_id")
                if server_id is not None:
                    floating_ips[server_id].append(floating_ip)
        if self.env.plugins.get("network", "nova") == "nova":
            name_key = "label"
        else:
            name_key = "name"
        networks = {network[name_key]: network for network in self.networks}
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
        plugin = self.env.plugins.get("network", "nova")
        if plugin == "nova":
            networks = self.env.cloud.nova.networks.list()
            return filter_prefixed(networks, key="label")
        elif plugin == "neutron":
            networks = self.env.cloud.neutron.list_networks()["networks"]
            return filter_prefixed(networks, convert_fn=lambda x: x)
        else:
            assert False

    @base.Collection(FloatingIP)
    def floating_ips(self):
        plugin = self.env.plugins["network"]
        if plugin == "nova":
            floating_ips = self.env.cloud.nova.floating_ips_bulk.list()
            for f in floating_ips:
                yield f.to_dict()
        elif plugin == "neutron":
            networks = {network["id"]: network for network in self.networks}
            fips = self.env.cloud.neutron.list_floatingips()["floatingips"]
            for floating_ip in fips:
                port_id = floating_ip["port_id"]
                if port_id is not None:
                    port = self.env.cloud.neutron.show_port(port_id)["port"]
                    floating_ip["fixed_ip"] = {
                        "id": port_id,
                        "address": floating_ip["fixed_ip_address"],
                        "network": networks[port["network_id"]],
                        "device_id": port["device_id"],
                    }
                else:
                    floating_ip["fixed_ip"] = {
                        "address": None,
                        "network": {"name": None},
                    }
                yield floating_ip

    @base.Collection(Image)
    def images(self):
        return filter_prefixed(self.env.cloud.glance.images.list(),
                               convert_fn=dict)

    @base.Collection(Volume)
    def volumes(self):
        volumes = self.env.cloud.cinder.volumes.list(
            search_opts={"all_tenants": 1})
        for volume in volumes:
            volume_info = volume._info
            display_name = volume_info.get("display_name", "") or ""
            if is_prefixed(display_name):
                yield volume_info

    delete = base.task(name="delete", requires=[
        tenants.each().delete,
        roles.each().delete,
        users.each().delete,
        volumes.each().delete,
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
        num_volumes = self.data["populate"].get("num_volumes", 0)
        volume_size = self.data["populate"].get("volume_size", 1)  # GB

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

        def server_volumes(tenant, server):
            if "volumes" in server:
                for volume in server["volumes"]:
                    yield dict(volume,
                               id=volume["display_name"])
            elif num_volumes:
                for _ in xrange(num_volumes):
                    ref = str(random.randint(1, 0x7fffffff))
                    name = "{}-{}".format(TEST_RESOURCE_PREFIX, ref)
                    volume = {
                        "id": name,
                        "display_name": name,
                        "size": volume_size,
                        "tenant": tenant,
                    }
                    tenant.setdefault("volumes", []).append(volume)
                    yield volume
            else:
                return

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
                volumes = list(server_volumes(tenant, server))
                server.update({
                    "tenant": tenant,
                    "user": {
                        "name": tenant["username"],
                        "tenant": tenant,
                    },
                    "floating_ips": [],
                    "fixed_ips": [],
                    "os-extended-volumes:volumes_attached": volumes,
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

    @base.Collection(Volume)
    def volumes(self):
        for tenant in self.tenants:
            for volume in tenant.get("volumes", ()):
                volume["id"] = volume["display_name"]
                volume["tenant"] = tenant
                yield volume

    create = base.task(name="create", requires=[
        tenants.each().create,
        users.each().create,
        images.each().upload,
        flavors.each().create,
        security_groups.each().create,
        networks.each().create,
        servers.each().create,
        floating_ips.each().create,
        volumes.each().create,
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
