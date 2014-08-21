# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.

import logging

from taskflow.patterns import linear_flow

from pumphouse import task
from pumphouse.tasks import image as image_tasks


LOG = logging.getLogger(__name__)


class RetrieveImage(task.BaseCloudTask):
    def execute(self, image_id):
        image = self.cloud.glance.images.get(image_id)
        return image.to_dict()


class EnsureSnapshot(task.BaseCloudTask):
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
                            rebind=[server_binding]))
    flow.add(image_tasks.EnsureImage(src, dst,
                                     name=image_ensure,
                                     provides=image_ensure,
                                     rebind=[snapshot_ensure]))
    # FIXME(akscram): It looks like a broken factory.
    return flow, store
