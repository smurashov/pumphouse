from pumphouse.services import base
from glanceclient import Client
from keystoneclient.v2_0 import client

GLANCE_API_VERSION='1'

class Glance(base.Service):

    type = "image"

    @classmethod
    def get_client(cls, endpoint):
        k = client.Client(**endpoint)
        catalog = k.service_catalog.get_endpoints()
        glance_urls = catalog[cls.type][0]
        c = Client(GLANCE_API_VERSION,
                   endpoint=glance_urls['publicURL'],
                   token=k.auth_token)
        return c
