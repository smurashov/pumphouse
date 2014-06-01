from pumphouse import services


class Glance(services.Service):

    type = "image"

    def __init__(self, images=None):
        self.images = images or []

    def discovery(self, keystone):
        pass
