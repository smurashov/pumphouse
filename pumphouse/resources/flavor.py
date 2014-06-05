from pumphouse.resources import base
from pumphouse.services import nova

class FlavorsCollection(base.Collection):
    service = nova.Nova

    def discover(self):
        nova = self.service.client
        flavors_d = nova.flavors.list()
        for fl in flavors_d:
            self.elements.append(Flavor(fl.id, fl.name))

    def migrate(self):
        raise NotImplemented

class Flavor(base.Resource):
    service = nova.Nova

    def __init__(self, uuid, name, ram, disk, vcpus, is_public, extra_specs):
        self.uuid = uuid
        self.name = name
        self.ram = ram
        self.disk = disk
        self.vcpus = vcpus
        self.is_public = is_public
        self.extra_specs = extra_specs

    def __repr__(self):
        return("<Flavor(uuid={0}, name={1}, ram={2}, disk={3}, vcpus={4}, "
               "is_public={5})>"
               .format(self.uuid, self.name, self.ram, self.disk, self.vcpus,
                       self.is_public))

    @classmethod
    def discover(cls, client, uuid):
        try:
            fl = client.flavors.get(uuid)
        except Exception as exc:
            print("Exception while discovering resource {0}: {1}"
                  .format(str(cls), exc.message))
            return None
        return cls(fl.id,
                   fl.name,
                   fl.ram,
                   fl.disk,
                   fl.vcpus,
                   fl.is_public,
                   fl.get_keys())

    def migrate(self):
        nova = self.service.client
        return nova.flavors.create(self.name,
                                   self.ram,
                                   self.vcpus,
                                   self.disk,
                                   self.uuid,
                                   None, None, None,
                                   self.is_public)
