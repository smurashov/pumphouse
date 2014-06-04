class Resource(object):

    service = None

    def __init__(self, resource_class, uuid):
        self.uuid = uuid

    def __eq__(self, other):
        return self.uuid == other.uuid and self.name == other.name

    def __repr__(self):
        return "<Resource(uuid={0}, name={1})>".format(self.uuid, self.name)

    @classmethod
    def defined_resources(cls):
        return dict(
            (sub.__name__, sub)
            for sub in cls.__subclasses__()
            if sub.__name__ is not 'Resource')

    @classmethod
    def discover(cls, client, uuid):
        raise NotImplemented

class Collection(object):

    service = None

    def __init__(self):
        self.elements = []
