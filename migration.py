import argparse
import yaml
import logging

from novaclient.v1_1 import client as nova_client
from novaclient import exceptions as nova_excs

from keystoneclient.v2_0 import client as keystone_client

from glanceclient import client as glance


LOG = logging.getLogger(__name__)


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f.read())


def get_parser():
    parser = argparse.ArgumentParser(description="Migration resources through "
                                                 "OpenStack clouds.")
    parser.add_argument("config",
                        type=safe_load_yaml,
                        help="Configuration of cloud endpoints and a "
                             "strategy.")
    return parser


def read_configuration(stream):
    with stream as f:
        return yaml.safe_load(f.read())


def migrate_flavor(mapping, src, dst, id):
    f0 = src.nova.flavors.get(id)
    if f0.id in mapping:
        LOG.warn("Skipped because mapping: %s", f0._info)
        return dst.nova.flavors.get(mapping[f0.id])
    try:
        f1 = dst.nova.flavors.get(f0)
    except nova_excs.NotFound:
        f1 = dst.nova.flavors.create(f0.name, f0.ram, f0.vcpus, f0.disk,
                                     flavorid=f0.id,
                                     ephemeral=f0.ephemeral,
                                     swap=f0.swap or 0,
                                     rxtx_factor=f0.rxtx_factor,
                                     is_public=f0.is_public)
        LOG.info("Created: %s", f1._info)
    else:
        LOG.warn("Already exists: %s", f1._info)
    return f1


def migrate_image(src, dst, id):
    def upload(src_image, dst_image):
        data = src.glance.images.data(src_image.id)
        dst.glance.images.upload(dst_image.id, data,
                                 image_size=src_image.size)
        LOG.info("Uploaded image: %s -> %s", src_image, dst_image)

    def create(image, **kwargs):
        new = dst.glance.images.create(disk_format=image.disk_format,
                                       container_format=image.container_format,
                                       visibility=image.visibility,
                                       min_ram=image.min_ram,
                                       min_disk=image.min_disk,
                                       name=image.name,
                                       protected=image.protected,
                                       **kwargs)
        LOG.info("Create image: %s", new)
        return new

    i0 = src.glance.images.get(id)
    if i0.id in mapping:
        LOG.warn("Skipped because mapping: %s", i0._info)
        return dst.glance.images.get(mapping[i0.id])
    imgs1 = dict([(i.checksum, i) for i in dst.glance.images.list()])
    if i0.checksum not in imgs1:
        params = {}
        if hasattr(i0, "kernel_id"):
            LOG.info("Found kernel image: %s", i0.kernel_id)
            ik1 = migrate_image(mapping, src, dst, i0.kernel_id)
            params["kernel_id"] = ik1["id"]
        if "ramdisk_id" in i0:
            LOG.info("Fround ramdisk image: %s", i0.ramdisk_id)
            ir0 = migrate_image(mapping, src, dst, i0.ramdisk_id)
            params["ramdisk_id"] = ir0["id"]
        i1 = create(dst, i0, **params)
        upload(i0, i1)
    else:
        i1 = imgs1.get(i0.checksum)
        LOG.info("Already present: %s", i1)
    return i1


def migrate_server(mapping, src, dst, id):
    s0 = src.nova.servers.get(id)
    svrs1 = dst.nova.servers.list()
    if s0.id in mapping:
        LOG.warn("Skipped because mapping: %s", s0._info)
        return dst.nova.servers.get(mapping[s0.id])
    f1 = migrate_flavor(mapping, src, dst, s0.flavor["id"])
    i1 = migrate_image(mapping, src, dst, s0.image["id"])
    try:
        src.nova.servers.suspend(s0)
        LOG.info("Suspended: %s", s0)
        try:
            s1 = dst.nova.servers.create(s0.name, i1, f1)
        except:
            LOG.exception("Failed to create server: %s", s0)
            raise
        else:
            src.nova.servers.delete(s0)
            LOG.info("Deleted: %s", s0)
    except:
        LOG.exception("Error occured in migration: %s", s0)
        src.nova.servers.resume(s0)
        raise
    mapping[s0.id] = s1.id
    LOG.info("Created: %s", s1._info)
    return s1


class Cloud(object):
    def __init__(self, endpoint):
        self.nova = nova_client.Client(endpoint["username"],
                                       endpoint["password"],
                                       endpoint["tenant_name"],
                                       endpoint["auth_url"],
                                       "compute")
        self.keystone = keystone_client.Client(**endpoint)
        g_endpoint = self.keystone.service_catalog.get_endpoints()["image"][0]
        self.glance = glance.Client("2",
                                    endpoint=g_endpoint["publicURL"],
                                    token=self.keystone.auth_token)


def main():
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)

    mapping = {}

    src = Cloud(args.config["source"]["endpoint"])
    dst = Cloud(args.config["destination"]["endpoint"])

    for server in src.nova.servers.list():
        migrate_server(mapping, src, dst, server.id)

    LOG.info("Migration mapping: %r", mapping)



if __name__ == "__main__":
    main()
