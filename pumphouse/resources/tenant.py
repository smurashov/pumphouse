from pumphouse.resources import base
from pumphouse.services import keystone

class Tenant(base.Resource):
    service = keystone.Keystone

    def __init__(self, uuid, name):
        super(Tenant, self).__init__(uuid, name)
        self.description = ''
        self.enabled = True

    def __repr__(self):
        return("<Tenant(uuid={0}, name={1}, description={2}, enabled={3})>"
               .format(self.uuid, self.name, self.description, self.enabled))

    def discover(self):
        keystone = self.service.client
        tt = keystone.tenant.get(self.uuid)
        self.description = tt.description
        self.enabled = tt.enabled

    def migrate(self):
        keystone = self.service.client
        return keystone.tenants.create(self.name, 
                                       self.description,
                                       self.enabled)
