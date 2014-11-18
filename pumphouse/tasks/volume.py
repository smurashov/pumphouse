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

from taskflow.patterns import graph_flow

from pumphouse import task
from pumphouse import events
from pumphouse import utils
from pumphouse import exceptions
from pumphouse.tasks import image as image_tasks


LOG = logging.getLogger(__name__)


class RetrieveVolume(task.BaseCloudTask):
    def execute(self, volume_id):
        volume = self.cloud.cinder.volumes.get(volume_id)
        return volume._info


class UploadVolume(task.BaseCloudTask):
    def execute(self, volume_info):
        volume_id = volume_info["id"]
        try:
            resp, upload_info = self.cloud.cinder.volumes.upload_to_image(
                volume_id,
                False,
                "volume-{}-image".format(volume_id),
                'bare',
                'raw')
        except Exception as exc:
            LOG.exception("Upload failed: %s", exc.message)
            raise exc
        image_id = upload_info["os-volume_upload_image"]["image_id"]
        try:
            image = self.cloud.glance.images.get(image_id)
        except exceptions.glance_excs.NotFound:
            LOG.exception("Image not found: %s", image_id)
            raise exceptions.NotFound()
        image = utils.wait_for(image.id,
                               self.cloud.glance.images.get,
                               value="active")
        self.upload_to_glance_event(dict(image))
        return image.id

    def upload_to_glance_event(self, image_info):
        LOG.info("Created: %s", image_info)
        events.emit("volume snapshot create", {
            "cloud": self.cloud.name,
            "id": image_info["id"],
            "name": image_info["name"],
            "status": "active",
        }, namespace="/events")


class CreateVolumeFromImage(task.BaseCloudTask):
    def execute(self, volume_info, image_info):
        image_id = image_info["id"]
        try:
            volume = self.cloud.cinder.volumes.create(
                volume_info["size"],
                display_name=volume_info["display_name"],
                display_description=volume_info["display_description"],
                volume_type=volume_info["volume_type"],
                imageRef=image_id)
        except Exception as exc:
            LOG.exception("Cannot create: %s", volume_info)
            raise exc
        else:
            volume = utils.wait_for(volume.id,
                                    self.cloud.cinder.volumes.get,
                                    value="available",
                                    timeout=120,
                                    check_interval=10)
            self.create_volume_event(volume._info)
        return volume._info

    def create_volume_event(self, volume_info):
        LOG.info("Created: %s", volume_info)
        events.emit("volume create", {
            "cloud": self.cloud.name,
            "id": volume_info["id"],
            "status": "active",
            "display_name": volume_info["display_name"],
            "tenant_id": volume_info["os-vol-tenant-attr:tenant_id"],
            "host_id": volume_info["os-vol-host-attr:host"],
            "attachment_server_ids": [],
        }, namespace="/events")


def migrate_detached_volume(context, volume):
    volume_binding = "volume-{}".format(volume.id)
    volume_retrieve = "{}-retrieve".format(volume_binding)
    volume_upload = "{}-upload".format(volume_binding)
    image_ensure = "{}-image-ensure".format(volume_binding)
    user_id = "none"
    user_ensure = "user-{}-ensure".format(user_id)
    context.store[user_ensure] = None
    volume_ensure = "{}-ensure".format(volume_binding)

    flow = graph_flow.Flow("migrate-{}".format(volume_binding))
    flow.add(RetrieveVolume(context.src_cloud,
                            name=volume_binding,
                            provides=volume_binding,
                            rebind=[volume_retrieve]))
    flow.add(UploadVolume(context.src_cloud,
                          name=volume_upload,
                          provides=volume_upload,
                          rebind=[volume_binding]))
    flow.add(image_tasks.EnsureSingleImage(context.src_cloud,
                                           context.dst_cloud,
                                           name=image_ensure,
                                           provides=image_ensure,
                                           rebind=[volume_upload,
                                                   user_ensure]))
    flow.add(CreateVolumeFromImage(context.dst_cloud,
                                   name=volume_ensure,
                                   provides=volume_ensure,
                                   rebind=[volume_binding,
                                           image_ensure]))
    context.store[volume_retrieve] = volume.id
    return flow
