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
from pumphouse import exceptions
from pumphouse import utils


LOG = logging.getLogger(__name__)


class RetrieveVolume(task.BaseCloudTask):
    def execute(self, volume_id):
        volume = self.cloud.cinder.volumes.get(volume_id)
        return volume._info


class UploadVolume(task.BaseCloudTask):
    def execute(self, volume_id):
        try:
            resp, upload_info = self.cloud.cinder.volumes.upload_to_glance(
                volume_id)
        except Exception:
            raise
        if resp.ok:
            image_id = upload_info["os-volume_upload_image"]["image_id"]
            image = self.cloud.glance.images.get(image_id)
            image = utils.wait_for(image.id,
                                   self.cloud.glance.images.get,
                                   value="active")
            self.upload_to_glance_event(image.to_dict())
        else:
            raise Exception(resp.reason)
        return image.to_dict()

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
        except Exception:
            raise
        else:
            volume = utils.wait_for(volume.id,
                                    self.cloud.cinder.volumes.get,
                                    value="active")
            self.create_volume_event(volume._info)
        return volume._info

    def create_volume_event(self, volume_info):
        LOG.info("Created: %s", volume_info)
        events.emit("volume create", {
            "cloud": self.cloud.name,
            "id": volume_info["id"],
            "status": "active",
            "display_name": volume_info["display_name"],
            "tenant_id": volume_info["project_id"],
            "host_id": volume_info["os-vol-host-attr:host"],
            "attachment_server_ids": [],
        }, namespace="/events")
