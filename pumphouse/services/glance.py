from pumphouse.services import base
from glanceclient.v1 import client


class Glance(base.Service):

    type = "image"

    def __init__(self, images=None):
        self.images = images or []

    @classmethod
    def get_client(cls, endpoint):
        pass
