from pumphouse import services


class Nova(services.Service):

    type = "compute"

    def __init__(self, servers=None, flavors=None):
        self.servers = servers or []
        self.flavors = flavors or []

    def discover(self, endpoint):
        flavor_d = DiscoveryFlavors(endpoint)
