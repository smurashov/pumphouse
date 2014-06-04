from pumphouse.services import base
from novaclient.v1_1 import client


class Nova(base.Service):

    type = "compute"

    @classmethod
    def get_client(cls, endpoint):
        c = client.Client(endpoint['username'],
                          endpoint['password'],
                          endpoint['tenant_name'],
                          endpoint['auth_url'])
        print c
        return c
