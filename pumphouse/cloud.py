from pumphouse import services


class Cloud(object):

    def __init__(self, services=None):
        self.services = services or []

    @classmethod
    def discover(cls, endpoint):
        discover = DiscoveryServices(endpoint)
        services = list(dicovery.discover())
        return cls(services=services)


class CloudDiscovery(object):

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.keystone = keystone_client.Client(**endpoint)

    def discover(self):
        known_services = services.Service.defined_services()
        catalog = self.keystone.services.list()
        for service_ref in catalog:
            if service_ref.type in known_services.keys():
                Service = known_services[service_ref.type]
                yield Service.discover(self.endpoint)
