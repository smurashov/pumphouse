import collections
import logging
import sqlalchemy as sqla

from novaclient.v1_1 import client as nova_client
from keystoneclient.v2_0 import client as keystone_client
from glanceclient import client as glance


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


class Namespace(object):
    __slots__ = ("username", "password", "tenant_name", "auth_url")

    def __init__(self,
                 username=None,
                 password=None,
                 tenant_name=None,
                 auth_url=None):
        self.username = username
        self.password = password
        self.tenant_name = tenant_name
        self.auth_url = auth_url

    def to_dict(self):
        return dict((attr, getattr(self, attr)) for attr in self.__slots__)

    def restrict(self, *nspace, **attrs):
        def nspace_getter(x, y, z):
            return getattr(x, y, z)

        def attrs_getter(x, y, z):
            return x.get(y, z)

        def restrict_by(attrs, getter):
            namespace = Namespace()
            for attr in self.__slots__:
                value = getter(attrs, attr, None)
                if value is None:
                    value = getattr(self, attr)
                setattr(namespace, attr, value)
            return namespace
        return restrict_by(*((nspace[0], nspace_getter)
                             if nspace else
                             (attrs, attrs_getter)))

    def __repr__(self):
        return ("<Namespace(username={!r}, password={!r}, tenant_name={!r}, "
                "auth_url={!r})>"
                .format(self.username, self.password, self.tenant_name,
                        self.auth_url))

    def __eq__(self, other):
        return (self.username == other.username and
                self.password == other.password and
                self.tenant_name == other.tenant_name and
                self.auth_url == other.auth_url)


class Cloud(object):

    """Describes a cloud involved in migration process

    Both source and destination clouds are instances of this class.

    :param cloud_ns:    an administrative credentials namespace of the cloud
    :type cloud_ns:     object
    :param user_ns:     a restricted user credentials namespace
    :type user_ns:      object
    :param identity:    object containing access credentials
    """

    def __init__(self, cloud_ns, user_ns, identity):
        self.identity = identity
        self.cloud_ns = cloud_ns
        self.user_ns = user_ns
        self.access_ns = cloud_ns.restrict(user_ns)
        self.nova = nova_client.Client(self.access_ns.username,
                                       self.access_ns.password,
                                       self.access_ns.tenant_name,
                                       self.access_ns.auth_url,
                                       "compute")
        self.keystone = keystone_client.Client(**self.access_ns.to_dict())
        g_endpoint = self.keystone.service_catalog.get_endpoints()["image"][0]
        self.glance = glance.Client("2",
                                    endpoint=g_endpoint["publicURL"],
                                    token=self.keystone.auth_token)

    def restrict(self, user_ns):
        return Cloud(self.cloud_ns, user_ns, self.identity)

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


def make_client(config, target, cloud_driver, identity_driver):
    identity = identity_driver(**config["identity"])
    cloud = cloud_driver.from_dict(endpoint=config["endpoint"],
                                   identity=identity)
    LOG.info("Cloud client initialized for endpoint: %s",
             config["endpoint"]["auth_url"])
    return cloud
