from pumphouse.services import base
from novaclient.v1_1 import client


class Nova(base.Service):

    type = "compute"

    def __init__(self, servers=None, flavors=None):
        self.client = self.get_client(self.cloud.endpoint)

    @classmethod
    def get_client(cls, endpoint):
        c = client.Client(endpoint['username'],
                          endpoint['password'],
                          endpoint['tenant_name'],
                          endpoint['auth_url'])
        print c
        return c
