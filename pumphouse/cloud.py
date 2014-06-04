import copy

from pumphouse.services.base import Service
from pumphouse.resources.base import Resource


class Cloud(object):

    def __init__(self, endpoint, services=None, resources=None):
        self.endpoint = endpoint
        self.services = services or dict(Service.discover(self.endpoint))

    def discover(self, resource_class, resource_id):
        resource_classes = Resource.defined_resources()
        if resource_class in resource_classes:
            service_name = resource_classes[resource_class].service.__name__
            if service_name.lower() in self.services:
                client = self.services[service_name.lower()]
                resource = resource_classes[resource_class].discover(client, resource_id)
                return resource
            else:
                return None

    def _convert(self, resource):
        nresource = copy.deepcopy(resource)
        nresource.service = self.services(resource.service.type)
        return nresource
    
    @classmethod
    def migrate(cls, resource):
        src = resource
        dst = cls._convert(src)
        dst = cls.discover(dst)
        if src == dst:
            return dst
        elif not dst:
            dst.migrate()
        else:
            
            raise Exception('Duplicate resources exist in src and dst clouds')
