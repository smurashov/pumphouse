from pumphouse.resources import base
from pumphouse.services import glance


class Image(base.Resource):
    service = glance.Glance

    def __init__(self, uuid, name, disk_format, container_format,
                 owner, size, checksum):
        self.uuid = uuid
        self.name = name
        self.disk_format = disk_format
        self.container_format = container_format
        self.owner = base.Resource.discover('Tenant', owner)
        self.size = size
        self.checksum = checksum

    def __repr__(self):
        return ("<Image(uuid={0}, name={1}, format={2}, status={3!r}, "
                "is_public={4!r}, kernel={5!r}, ramdisk={6!r})>"
                .format(self.uuid, self.name, self.format, self.status,
                        self.is_public, self.kernel, self.ramdisk))

    @classmethod
    def discover(cls, client, uuid):
        try:
            img = client.images.get(uuid)
        except Exception as exc:
            print("Exception while discovering resource {0}: {1}"
                  .format(str(cls), exc.message))
            return None

        return cls(img.id,
                   img.name,
                   img.disk_format,
                   img.container_format,
                   img.owner,
                   img.size,
                   img.checksum)
