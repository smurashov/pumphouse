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
from pumphouse.tasks import image as image_tasks


LOG = logging.getLogger(__name__)


class EnsureSnapshot(task.BaseCloudTask):
    def execute(self, server_id):
        try:
            snapshot_id = self.cloud.servers.create_image(
                server_id,
                "pumphouse-snapshot-{}"
                .format(server_id))
        except Exception:
            LOG.exception("Snapshot failed: %s", server_id)
            raise
        else:
            snapshot = self.cloud.glance.images.get(snapshot_id)
            snapshot = utils.wait_for(snapshot.id,
                                      self.cloud.glance.images.get,
                                      value='active')
            LOG.info("Created: %s", snapshot)
            return snapshot.id


def migrate_snapshot(src, dst, store, server_id):
    server_binding = "server-{}".format(server_id)
    snapshot_binding = "snapshot-{}".format(server_id)
    snapshot_ensure = "snapshot-{}-ensure".format(server_id)
    flow = linear_flow.Flow("migrate-ephemeral-storage-server-{}"
                            .format(server_id))
    flow.add(EnsureSnapshot(src,
                            name=snapshot_binding,
                            provides=snapshot_binding,
                            rebind=[server_binding]))
    flow.add(image_tasks.EnsureImage(src, dst,
                                     name=snapshot_ensure,
                                     provides=snapshot_ensure,
                                     rebind=[snapshot_binding]))
    return flow, store
