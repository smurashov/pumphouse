import logging

from taskflow.patterns import linear_flow

from pumphouse import tasks
from pumphouse import exceptions
from pumphoust import utils


LOG = logging.getLogger(__name__)


class RetrieveImage(tasks.BaseCloudTask):
    def retrieve(self, image_id):
        image = self.cloud.glance.images.get(image_id)
        return image.to_dict()            


class EnsureSnapshot(tasks.BaseCloudTask):
    def execute(self, server_info):
        try:
            snapshot_id = self.cloud.servers.create_image(
                server_info["id"],
                "pumphouse-snapshot-{}"
                .format(server_info["id"]))
        except Exception:
            LOG.exception("Snapshot failed: %s", server_info)
            raise
        else:
            snapshot = self.cloud.glance.images.get(snapshot_id)
            LOG.info("Created: %s", snapshot)
            return snapshot_id


def migrate_ephemeral_storage(src, dst, store, server_id):
    server_binding = "server-{}".format(server_id)
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)
    image_ensure = "image-{}-ensure".format(server_id)
    flow = linear_flow.Flow("migrate-ephemeral-storage-server-{}"
                            .format(server_id))
    flow.add(EnsureSnapshot(src,
                            name=snapshot_ensure,
                            provides=snapshot_ensure,
                            requires=[server_binding]))
    flow.add(tasks.EnsureImage(src, dst,
                               name=image_ensure,
                               provides=image_ensure,
                               requires=[snapshot_ensure]))
