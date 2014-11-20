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
from pumphouse import utils
from pumphouse import events
from pumphouse.tasks import image as image_tasks


LOG = logging.getLogger(__name__)


class SnapshotServer(task.BaseCloudTask):

    def execute(self, server_info):
        server_id = server_info["id"]
        snapshot_name = "{}-snapshot-{}".format(server_info["name"], server_id)
        try:
            snapshot_id = self.cloud.nova.servers.create_image(
                server_id, snapshot_name)
        except Exception:
            LOG.exception("Snapshot failed for server: %s", server_id)
            raise
        else:
            snapshot = self.cloud.glance.images.get(snapshot_id)
            snapshot = utils.wait_for(snapshot.id,
                                      self.cloud.glance.images.get,
                                      value="active")
            LOG.info("Created: %s", snapshot)
            self.created_event(snapshot)
            return snapshot.id

    def created_event(self, snapshot):
        events.emit("create", {
            "id": snapshot["id"],
            "type": "image",
            "cloud": self.cloud.name,
            "action": "uploading",
            "data": dict(snapshot),
        }, namespace="/events")


def migrate_snapshot(context, server):
    server_id = server.id
    server_binding = "server-{}".format(server_id)
    snapshot_binding = "snapshot-{}".format(server_id)
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)
    user_ensure = "user-{}-ensure".format(server.user_id)
    flow = linear_flow.Flow("migrate-ephemeral-storage-server-{}"
                            .format(server_id))
    flow.add(SnapshotServer(context.src_cloud,
                            name=snapshot_binding,
                            provides=snapshot_binding,
                            rebind=[server_binding]))
    flow.add(image_tasks.EnsureSingleImage(context.src_cloud,
                                           context.dst_cloud,
                                           name=snapshot_ensure,
                                           provides=snapshot_ensure,
                                           rebind=[snapshot_binding,
                                                   user_ensure]))
    return flow
