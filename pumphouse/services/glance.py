from pumphouse.services import base
from glanceclient.v1 import client


class Glance(base.Service):

    type = "image"

    @classmethod
    def get_client(cls, endpoint):
        pass
