import argparse
import yaml


# TODO(akscram): A proper feature with auto-discovering API version
#                should be used here.
#from keystoneclient import client as keystone_client
from keystoneclient.v2_0 import client as keystone_client
from novaclient.v1_1 import client as nova_client


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f.read())


def get_parser():
    parser = argparse.ArgumentParser(description="Migration resources through "
                                                 "OpenStack clouds.")
    parser.add_argument("config",
                        type=safe_load_yaml,
                        help="Configuration of cloud endpoints and a "
                             "strategy.")
    return parser


def read_configuration(stream):
    with stream as f:
        return yaml.safe_load(f.read())


class Cloud(object):
    def __init__(self, services=None):
        self.services = services or []

    @classmethod
    def discover(cls, endpoint):
        discover = DiscoveryServices(endpoint)
        services = list(dicovery.discover())
        return cls(services=services)

# TODO(akscram): To avoid merge conflics.
class Discovery(object):
    def __init__(self, config):
        self.username = config['username']
        self.password = config['password']
        self.auth_url = config['auth_url']
        self.tenant = config['tenant']


class DiscoveryServices(object):
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.keystone = keystone_client.Client(**endpoint)

    def discover(self):
        known_services = Service.defined_services()
        catalog = self.keystone.services.list()
        for service_ref in catalog:
            Service = known_services.get(service_ref.type)
            if Service is not None:
                yield Service.discover(self.endpoint)


class DiscoveryNovaResources(object):
    def __init__(self, endpoint):
        self.nova = nova_client.Client(endpoint["username"],
                                       endpoint["password"],
                                       endpoint["tenant_name"],
                                       endpoint["auth_url"])


class DiscoveryServers(DiscoveryNovaResources):
    def discover(self):
        pass


class DiscoveryFlavors(DiscoveryNovaResources):
    def discover(self):
        pass


class Pump(object):
    def __init__(self, source, destination):
        pass


class Service(object):
    type = None

    @classmethod
    def defined_services(cls):
        return dict(
            (sub.type, sub)
            for sub in cls.__subclasses__()
            if sub.type is not None
        )


class Nova(Service):
    type = "compute"

    def __init__(self, servers=None, flavors=None):
        self.servers = servers or []
        self.flavors = flavors or []

    def discover(self, endpoint):
        flavor_d = DiscoveryFlavors(endpoint)


class Glance(Service):
    type = "image"

    def __init__(self, images=None):
        self.images = images or []

    def discovery(self, keystone):
        pass


class Resource(object):
    service = None

    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name

    def __eq__(self, other):
        return self.uuid == other.uuid and self.name == other.name

    def __repr__(self):
        return "<Resource(uuid={0}, name={1})>".format(self.uuid, self.name)


class Image(Resource):
    service = Glance

    def __init__(self, uuid, name, format, status, is_public,
                 kernel=None, ramdisk=None):
        super(Image, self).__init__(uuid, name)
        self.format = format
        self.status = status
        self.is_public = is_public
        self.kernel = kernel
        self.ramdisk = ramdisk

    def __repr__(self):
        return ("<Image(uuid={0}, name={1}, format={2}, status={3!r}, "
                "is_public={4!r}, kernel={5!r}, ramdisk={6!r})>"
                .format(self.uuid, self.name, self.format, self.status,
                        self.is_public, self.kernel, self.ramdisk))


class Flavor(Resource):
    service = Nova


class Server(Resource):
    service = Nova

    def __init__(self, uuid, name, flavor, image, addresses):
        super(Server, self).__init__(uuid, name)
        self.flavor = flavor
        self.image = image
        self.addresses = addresses

    def __repr__(self):
        return ("<Server(uuid={0}, name={1}, flavor={2!r}, image={3!r}, "
                "addresses={4})>"
                .format(self.uuid, self.name, self.flavor, self.image,
                        self.addresses))


def main():
    parser = get_parser()
    args = parser.parse_args()

    source = discovery(args.config["source"]["endpoint"])
    destination = discovery(args.config["destination"]["endpoint"])


if __name__ == "__main__":
    main()
