from . import base

class FlavorsCollection(base.Collection):
    service = Nova

    def discover(self):
        nova = self.service.client
        flavors_d = nova.flavors.list()
        for fl in flavors_d:
            self.elements.append(Flavor(fl.id, fl.name))

    def migrate(self):
        raise NotImplemented

class Flavor(base.Resource):
    service = Nova

    def __init__(self, uuid, name, **kwargs):
        super(Flavor, self).__init__(uuid, name)
        self.id = uuid
        self.name = name
        self.ram = kwargs['ram'] or None
        self.disk = kwargs['disk'] or None
        self.vcpus = kwargs['vcpus'] or None
        self.is_public = kwargs['os-flavor-access:is_public'] or True
        self.extra_specs = kwargs['extra_specs'] or []

    def __repr__(self):
        return("<Flavor(uuid={0}, name={2}, ram={3}, disk={4}, vcpus={5}, "
               "is_public={6})>"
               .format(self.uuid, self.name, self.ram, self.disk, self.vcpus,
                       self.is_public))

    def discover(self):
        nova = self.service.client
        fl = nova.flavors.get(self.id)
        self.ram = fl.ram
        self.disk = fl.disk
        self.vcpus = fl.vcpus
        self.is_public = fl.is_public
        self.extra_specs = fl.get_keys()

    def migrate(self):
        nova = self.service.client
        return nova.flavors.create(self.name,
                                   self.ram,
                                   self.vcpus,
                                   self.disk,
                                   self.id,
                                   None, None, None,
                                   self.is_public)
