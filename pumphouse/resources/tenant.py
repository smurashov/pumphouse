from pumphouse.resources import base
from pumphouse.services import keystone

class Tenant(base.Resource):
    service = keystone.Keystone

    def __repr__(self):
        return("<Tenant(uuid={0}, name={1}, description={2}, enabled={3})>"
               .format(self.uuid, self.name, self.description, self.enabled))

    @classmethod
    def discover(cls, client, uuid):
        try:
            tt = client.tenants.get(uuid)
        except Exception as exc:
            print("Exception while discovering resource {0}: {1}"
                  .format(str(cls), exc.message))
            return None
        cls.uuid = tt.id
        cls.name = tt.name
        cls.description = tt.description
        cls.enabled = tt.enabled
        return cls

    def migrate(self):
        keystone = self.service.client
        return keystone.tenants.create(self.name, 
                                       self.description,
                                       self.enabled)
