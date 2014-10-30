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
import os
import random
import tempfile
import urllib

from novaclient import exceptions as nova_excs

from pumphouse.tasks import base
from pumphouse import utils


TEST_IMAGE_URL = ("http://download.cirros-cloud.net/0.3.2/"
                  "cirros-0.3.2-x86_64-disk.img")
TEST_RESOURCE_PREFIX = "pumphouse-"


def is_prefixed(string):
    return string.startswith(TEST_RESOURCE_PREFIX)


def filter_prefixed(lst, dict_=False):
    return [(dict(e) if dict_ else e.to_dict())
            for e in lst if is_prefixed(e.name)]


def make_kwargs(**kwargs):
    return {k: v for k, v in kwargs.iteritems() if v is not None}


class Tenant(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        return data["name"]

    @base.task
    def create(self):
        self.tenant = self.env.cloud.keystone.tenants.create(
            self.tenant["name"],
            **make_kwargs(
                description=self.tenant.get("description"),
                enabled=self.tenant.get("enabled"),
            )
        ).to_dict()

    @base.task
    def delete(self):
        self.env.cloud.keystone.tenants.delete(self.tenant["id"])


class Role(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        return data["name"]

    @base.task
    def create(self):
        self.role = self.cloud.keystone.role.create(
            name=self.role["name"],
        ).to_dict()

    @base.task
    def delete(self):
        self.env.cloud.keystone.roles.delete(self.role["id"])


class User(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        return data["name"]

    @Tenant()
    def tenant(self):
        return self.user["tenant"]

    @base.task(requires=[tenant.create])
    def create(self):
        self.user = self.env.cloud.keystone.users.create(
            name=self.user["name"],
            password="default",
            tenant_id=self.tenant["id"],
        ).to_dict()

    @base.task
    def delete(self):
        self.env.cloud.keystone.users.delete(self.user["id"])


class Flavor(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        return data["name"]

    @base.task
    def create(self):
        self.flavor = cloud.nova.flavors.create(
            self.flavor["name"],
            self.flavor["ram"],
            self.flavor["vcpu"],
            self.flavor["disk"],
            **make_kwargs(
                flavorid=self.flavor.get("id"),
                ephemeral=self.flavor.get("ephemeral"),
                swap=self.flavor.get("swap"),
                rxtx_factor=self.flavor.get("rxtx_factor"),
                is_public=self.flavor.get("is_public"),
            )
        ).to_dict()

    @base.task
    def delete(self):
        self.env.cloud.nova.flavors.delete(self.flavor["id"])


class CachedImage(base.Resource):
    @classmethod
    def get_id_for(cls, data):
        return data["url"]

    @base.task
    def cache(self):
        f = tempfile.TemporaryFile()
        img = urllib.urlopen(self.cachedimage["url"])
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

        self.cachedimage = {"file": f}


class Image(base.Resource):
    @CachedImage()
    def cached_image(self):
        return {"url": self.image["url"]}

    @base.task(requires=[cached_image.cache])
    def create(self):
        # TODO(yorik-sar): split into create and upload once we have support
        # for requirements between tasks within one resource
        image = self.image.copy()
        image.pop("url")
        image.setdefault("visibility", "public")
        image = self.env.cloud.glance.images.create(**image)
        self.image = image = dict(image)
        # upload starts here
        clone_fd = os.dup(self.cached_image["file"].fileno())
        try:
            f = os.fdopen(clone_fd)
            self.env.cloud.glance.images.upload(image["id"], f)
        finally:
            os.close(clone_fd)
        image = self.env.cloud.glance.images.get(image["id"])
        self.image = dict(image)

    @base.task
    def delete(self):
        self.env.cloud.glance.images.delete(self.image["id"])


class Server(base.Resource):
    @Tenant()
    def tenant(self):
        try:
            return {"id": self.server["tenant_id"]}
        except KeyError:
            return self.server["tenant"]

    @User()
    def user(self):
        return self.server["user"]

    @Image()
    def image(self):
        return self.server["image"]

    @Flavor()
    def flavor(self):
        return self.server["flavor"]

    @base.task(requires=[image.create, tenant.create, flavor.create,
                         user.create])
    def create(self):
        cloud = self.env.cloud.restrict(
            username=self.user["name"],
            password="default",
            tenant_name=self.tenant["name"],
        )
        servers = cloud.nova.servers
        server = servers.create(
            self.server["name"],
            self.image["id"],
            self.flavor["id"],
        )
        server = utils.wait_for(server.id, servers.get, value="ACTIVE")
        self.server = server.to_dict()

    @base.task(before=[tenant.delete])
    def delete(self):
        self.env.cloud.nova.servers.delete(self.server["id"])
        utils.wait_for(self.server["id"], self.env.cloud.nova.servers.get,
                       stop_excs=(nova_excs.NotFound,))


class CleanupWorkload(base.Resource):
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
        return filter_prefixed(servers)

    @base.Collection(Flavor)
    def flavors(self):
        return filter_prefixed(self.env.cloud.nova.flavors.list())

    @base.Collection(Image)
    def images(self):
        return filter_prefixed(self.env.cloud.glance.images.list(), dict_=True)

    delete = base.task(name="delete", requires=[
        tenants.each().delete,
        roles.each().delete,
        users.each().delete,
        servers.each().delete,
        flavors.each().delete,
        images.each().delete,
    ])


def gen_to_list(f):
    @functools.wraps(f)
    def inner(*args, **kwargs):
        return list(f(*args, **kwargs))
    return inner


class SetupWorkload(base.Resource):
    @base.Collection(Tenant)
    @gen_to_list
    def tenants(self):
        tenants = self.setup["workloads"].get("tenants")
        if tenants is not None:
            for tenant in tenants:
                yield tenant
            return
        for i in xrange(self.setup["populate"].get("num_tenants", 2)):
            tenant_ref = str(random.randint(1, 0x7fffffff))
            yield {
                "name": "{}-{}".format(TEST_RESOURCE_PREFIX, tenant_ref),
                "description": "pumphouse test tenant {}".format(tenant_ref),
                "username": "{}-user-{}"
                            .format(TEST_RESOURCE_PREFIX, tenant_ref),
            }

    @base.Collection(User)
    @gen_to_list
    def users(self):
        users = self.setup["workloads"].get("users")
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
        images = self.setup["workloads"].get("images")
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
        flavors = self.setup["workloads"].get("flavors")
        if flavors is not None:
            return flavors
        return [{
            "name": "{}-flavor".format(TEST_RESOURCE_PREFIX),
            "ram": 1024,
            "vcpu": 1,
            "disk": 5,
        }]

    @base.Collection(Server)
    @gen_to_list
    def servers(self):
        servers = self.setup["workloads"].get("servers")
        if servers is not None:
            for server in servers:
                yield server
            return
        for tenant in self.tenants:
            tenant_ref = tenant["name"].rsplit("-", 1)[-1]
            for i in xrange(self.setup["populate"].get("num_servers", 2)):
                server_ref = str(random.randint(1, 0x7fffffff))
                image = random.choice(self.images)
                flavor = random.choice(self.flavors)
                yield {
                    "name": "{}-{}".format(TEST_RESOURCE_PREFIX, server_ref),
                    "image": image,
                    "flavor": flavor,
                    "tenant": tenant,
                    "user": {
                        "name": tenant["username"],
                        "tenant": tenant,
                    },
                }

    create = base.task(name="create", requires=[
        tenants.each().create,
        users.each().create,
        images.each().create,
        flavors.each().create,
        servers.each().create,
    ])


Environment = collections.namedtuple("Environment", ["cloud"])

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
        "populate": source_config["populate"],
        "workloads": source_config["workloads"],
    })
    runner.add(setup_workload.create)
    runner.run()
