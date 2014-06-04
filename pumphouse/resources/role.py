from pumphouse.resources import base
from pumphouse.services import keystone


class Role(base.Resource):
    service = keystone.Keystone

    def __init__(self, uuid, name):
        super(Tenant, self).__init__(uuid, name)
    
    def __repr__(self):
        return("<Role(uuid={0}, name={1})>".format(self.uuid, self.name))

    @classmethod
    def discover(self):
        keystone = self.service.client
        r = keystone.role.get(self.uuid)
    
    def migrate(self):
        keystone = self.service.client
        return keystone.role.create(self.name)
