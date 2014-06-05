from pumphouse.resources import base
from pumphouse.services import keystone

class Tenant(base.Resource):
    service = keystone.Keystone

    def __init__(self, uuid, name, description='', enabled=True):
        self.uuid = uuid
        self.name = name
        self.description = description
        self.enabled = enabled

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
        return cls(tt.id, tt.name, tt.description, tt.enabled)

    def migrate(self):
        keystone = self.service.client
        return keystone.tenants.create(self.name, 
                                       self.description,
                                       self.enabled)
