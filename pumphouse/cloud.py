from pumphouse import services


class Cloud(object):

    def __init__(self, services=None):
        self.services = services or []

    @classmethod
    def discover(cls, endpoint):
        discover = DiscoveryServices(endpoint)
        services = list(dicovery.discover())
        return cls(services=services)

    @classmethod
    def migrate(cls, resource):
        src = resource
        resource_type = src.__class__.__name__
        dst = cls._discover_resource(resource_type,
                             src.id,
                             src.name)
        if src == dst:
            return dst
        elif not dst:
            dst = copy.deepcopy(src)
            dst.service = cls.services(src.service.type)
            dst.migrate()
        else:
            raise Exception('Duplicate resources exist in src and dst clouds')

    def _discover_resource(self, resource_class, resource_id, resource_name):
        resource = 
        return resource.discover()


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
