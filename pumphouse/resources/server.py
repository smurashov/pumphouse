from pumphouse import base


class Server(base.Resource):
    service = Nova

    def __init__(self, uuid, name, flavor, image, addresses):
        super(Server, self).__init__(uuid, name)
        self.flavor = flavor
        self.image = image
        self.addresses = addresses

    def __repr__(self):
        return ("<Server(uuid={0}, name={1}, flavor={2!r}, image={3!r}, "
                "addresses={4})>"
                .format(self.uuid, self.name, self.flavor, self.image,
                        self.addresses))

