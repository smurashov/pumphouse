class Service(object):
    type = None

    @classmethod
    def defined_services(cls):
        return dict(
            (sub.type, sub)
            for sub in cls.__subclasses__()
            if sub.type is not None
        )

    @classmethod
    def get_client(cls, endpoint):
        raise NotImplemented

    @classmethod
    def discover(cls, endpoint):
        known_services = cls.defined_services()
        if 'identity' in known_services:
            keystone = known_services['identity'].get_client(endpoint)
        else:
            try:
                del endpoint['service_type']
            except KeyError:
                pass
            from keystoneclient.v2_0 import client
            keystone = client.Client(**endpoint)
        catalog = keystone.services.list()
        for service_ref in catalog:
            if service_ref.type in known_services.keys():
                Service = known_services[service_ref.type]
                yield (service_ref.name, Service.get_client(endpoint))
