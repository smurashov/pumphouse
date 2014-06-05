import copy

from pumphouse.services.base import Service
from pumphouse.resources.base import Resource


class Cloud(object):

    """Describes a cloud involved in migration process.

    Both source and destination clouds are instances of this class.

    :param endpoint: dictionary of OpenStack credentials to access the cloud.
    :type endpoint: dict
    :endpoint[username]: name of user with administrative permissions.
    :endpoint[password]: password of the user.
    :endpoint[tenant_name]: name of administrative tenant (usually 'admin').
    :endpoint[auth_url]: URL of Keystone service (e.g. 'http://example.com:5000/v2.0').

    """

    def __init__(self, endpoint, services=None, resources=None):
        self.endpoint = endpoint
        self.services = services or dict(Service.discover(self.endpoint))

    def discover(self, resource_class, resource_id):
    
        """Get resource by it's type and ID.

        :param resource_class: the type of resource to be returned, e.g. Flavor or Tenant.
        :type resource_class: str.
        :param resource_id: the UUID or ID of resource to be returned.
        :type resource_id: str.
        :returns: resource instance - resource discovered according to parameters.

        """

        resource_classes = Resource.defined_resources()
        print resource_classes
        if resource_class in resource_classes:
            service_name = resource_classes[resource_class].service.__name__
            if service_name.lower() in self.services:
                client = self.services[service_name.lower()]
                print client
                resource = resource_classes[resource_class].discover(client, resource_id)
                print resource
                return resource
            else:
                return None

    def _convert(self, resource):
        nresource = copy.deepcopy(resource)
        nresource.service = self.services(resource.service.type)
        return nresource
    
    @classmethod
    def migrate(cls, resource):
    
        """Migrates resource from source cloud to destination cloud.

        Must be called from the destination Cloud instance.
        :param resource: the instance of resource in the source cloud to be moved.
        :type resource: object.

        """

        src = resource
        dst = cls._convert(src)
        dst = cls.discover(dst)
        if src == dst:
            return dst
        elif not dst:
            dst.migrate()
        else:
            
            raise Exception('Duplicate resources exist in src and dst clouds')
