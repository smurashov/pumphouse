import argparse
import yaml


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
    def __init__(self, services):
        self.services = services

    def add_service(self, service):
        pass


class Discovery(object):
    def __init__(self, config):
        self.username = config['username']
        self.password = config['password']
        self.auth_url = config['auth_url']
        self.tenant = config['tenant']


class ServiceDiscovery(Discovery):
    pass



class Pump(object):
    def __init__(self, source, destination):
        pass


class Service(object):
    name = None


class Nova(Service):
    name = "nova"


class Glance(Service):
    name = "glance"


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
