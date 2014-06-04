from pumphouse.services import base
from keystoneclient.v2_0 import client

class Keystone(base.Service):

    type = "identity"

    def __init__(self):
        super(Keystone, self).__init__()
        self.client = self.get_client(self.cloud.endpoint)

    @classmethod
    def get_client(cls, endpoint):
        return client.Client(**endpoint)
