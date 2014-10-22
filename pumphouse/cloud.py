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
import logging
import sqlalchemy as sqla

from novaclient.v1_1 import client as nova_client
from keystoneclient.v2_0 import client as keystone_client
from glanceclient import client as glance
from cinderclient import client as cinder


LOG = logging.getLogger(__name__)


class Identity(collections.Mapping):
    select_query = sqla.text("SELECT id, password FROM user "
                             "WHERE id = :user_id")
    update_query = sqla.text("UPDATE user SET password = :password "
                             "WHERE id = :user_id")

    def __init__(self, connection):
        self.engine = sqla.create_engine(connection)
        self.hashes = {}

    def fetch(self, user_id):
        """Fetch a hash of user's password."""
        users = self.engine.execute(self.select_query, user_id=user_id)
        for _, password in users:
            self.hashes[user_id] = password
            return password

    def push(self):
        """Push hashes of users' passwords."""
        with self.engine.begin() as conn:
            for user_id, password in self.hashes.iteritems():
                conn.execute(self.update_query,
                             user_id=user_id, password=password)

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


NAMESPACE = collections.namedtuple("Namespace", ("username", "password",
                                                 "tenant_name", "auth_url"))


class Namespace(NAMESPACE):
    """Represents a set of credentials

    It's a container for credentials. Any instance of this class
    provides entire information for :class:`Cloud` initialization. Due
    to the fact that any user can be present in some tenants and some
    clouds, credentials can be restricted by them.

    :params username: a name of the user
    :params password: a password of the user
    :params tenant_name: a name of the project within scoped the user
    :params auth_url: an endpoint of the identity service
    """
    def to_dict(self):
        return self._asdict()

    def restrict(self, **attrs):
        creds = dict(self._asdict(), **attrs)
        namespace = self.__class__(**creds)
        return namespace

    def __repr__(self):
        return ("<Namespace(username={!r}, password={!r}, tenant_name={!r}, "
                "auth_url={!r})>"
                .format(self.username, "*" * len(self.password),
                        self.tenant_name, self.auth_url))


class Cloud(object):
    """Describes a cloud involved in migration process

    Both source and destination clouds are instances of this class.

    :param name:        a string with value which identify the cloud
    :type name:         str
    :param namespace:   a createndtials of the cloud object
    :type namespace:    :class:`Namespace`
    :param identity:    object containing access credentials
    :type identity:     :class:`Identity`
    """

    def __init__(self, name, namespace, identity):
        self.name = name
        self.namespace = namespace
        self.identity = identity
        self.nova = nova_client.Client(self.namespace.username,
                                       self.namespace.password,
                                       self.namespace.tenant_name,
                                       self.namespace.auth_url,
                                       "compute")
        self.keystone = keystone_client.Client(**self.namespace.to_dict())
        g_endpoint = self.keystone.service_catalog.get_endpoints()["image"][0]
        self.glance = glance.Client("2",
                                    endpoint=g_endpoint["publicURL"],
                                    token=self.keystone.auth_token)
        self.cinder = cinder.Client("1",
                                    self.namespace.username,
                                    self.namespace.password,
                                    self.namespace.tenant_name,
                                    self.namespace.auth_url)

    def ping(self):
        try:
            self.keystone.users.list(limit=1)
            self.nova.servers.list(limit=1)
            iter(self.glance.images.list(limit=1)).next()
        except Exception:
            LOG.exception("The client check is failed for cloud %r", self)
            return False
        else:
            return True

    def restrict(self, **kwargs):
        namespace = self.namespace.restrict(**kwargs)
        return self.__class__(self.name, namespace, self.identity)

    @classmethod
    def from_dict(cls, name, endpoint, identity):
        namespace = Namespace(
            username=endpoint["username"],
            password=endpoint["password"],
            tenant_name=endpoint["tenant_name"],
            auth_url=endpoint["auth_url"],
        )
        return cls(name, namespace, identity)

    def __repr__(self):
        return "<Cloud(namespace={!r})>".format(self.namespace)
