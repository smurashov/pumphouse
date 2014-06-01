from . import base


class Image(base.Resource):
    service = Glance

    def __init__(self, uuid, name, format, status, is_public,
                 kernel=None, ramdisk=None):
        super(Image, self).__init__(uuid, name)
        self.format = format
        self.status = status
        self.is_public = is_public
        self.kernel = kernel
        self.ramdisk = ramdisk

    def __repr__(self):
        return ("<Image(uuid={0}, name={1}, format={2}, status={3!r}, "
                "is_public={4!r}, kernel={5!r}, ramdisk={6!r})>"
                .format(self.uuid, self.name, self.format, self.status,
                        self.is_public, self.kernel, self.ramdisk))
