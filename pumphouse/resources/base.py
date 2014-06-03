class Discovery(object):
    def __init__(self, config):
        self.username = config['username']
        self.password = config['password']
        self.auth_url = config['auth_url']
        self.tenant = config['tenant']


class Resource(object):

    service = None

    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name

    def __eq__(self, other):
        return self.uuid == other.uuid and self.name == other.name

    def __repr__(self):
        return "<Resource(uuid={0}, name={1})>".format(self.uuid, self.name)


class Collection(object):

    service = None

    def __init__(self):
        self.elements = []
