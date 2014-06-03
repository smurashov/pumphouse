__all___ = ["Service", "Glance", "Nova"]


class Service(object):
    type = None

    @classmethod
    def defined_services(cls):
        return dict(
            (sub.type, sub)
            for sub in cls.__subclasses__()
            if sub.type is not None
        )
