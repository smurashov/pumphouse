from pumphouse.services import base
from keystoneclient.v2_0 import client

class Keystone(base.Service):

    type = "identity"

    @classmethod
    def get_client(cls, endpoint):
        return client.Client(**endpoint)
