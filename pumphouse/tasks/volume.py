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
from taskflow.task import Task

from pumphouse import task
from pumphouse import events
from pumphouse import utils
from pumphouse import exceptions
from pumphouse.tasks import utils as utils_tasks
from pumphouse.tasks import image as image_tasks


LOG = logging.getLogger(__name__)


class RetrieveVolume(task.BaseCloudTask):

    def execute(self, volume_id):
        volume = self.cloud.cinder.volumes.get(volume_id)
        return volume._info


class CreateVolumeSnapshot(task.BaseCloudTask):

    def execute(self, volume_info, timeout):
        volume_id = volume_info["id"]

        try:

            # TODO (sryabin) check the volume has been detached
            snapshot = self.cloud.cinder.volume_snapshots.create(volume_id)

        except Exception as e:
            LOG.exception("Can't create snapshot from volume: %s",
                          str(volume_info))

        snapshot = utils.wait_for(
            snapshot.id,
            self.cloud.cinder.volume_snapshots.get,
            value='available',
            timeout=timeout,
            error_value='error')

        return snapshot._info


class UploadVolume(task.BaseCloudTask):

    def execute(self, volume_info, timeout):
        volume_id = volume_info["id"]
        try:
            resp, upload_info = self.cloud.cinder.volumes.upload_to_image(
                volume_id,
                False,
                "pumphouse-volume-{}-image".format(volume_id),
                'bare',
                'qcow2')
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
                               value="active",
                               timeout=timeout)
        self.upload_to_glance_event(dict(image))
        return image.id

    def upload_to_glance_event(self, image_info):
        LOG.info("Created: %s", image_info)
        events.emit("create", {
            "id": image_info["id"],
            "cloud": self.cloud.name,
            "type": "image",
            "data": dict(image_info)
        }, namespace="/events")


class CreateVolumeTask(task.BaseCloudTask):
    def create_volume_event(self, volume_info):
        LOG.info("Created: %s", volume_info)
        host_id = volume_info.get("os-vol-host-attr:host", None)
        events.emit("create", {
            "id": volume_info["id"],
            "cloud": self.cloud.name,
            "type": "volume",
            "data": dict(volume_info,
                         host_id=host_id,
                         name=volume_info["display_name"],
                         server_ids=[att["server_id"]
                                     for att in volume_info["attachments"]]),
        }, namespace="/events")


class CreateVolumeFromImage(CreateVolumeTask):
    def execute(self, volume_info, image_info,
                user_info, tenant_info, timeout):
        image_id = image_info["id"]
        if user_info:
            restrict_cloud = self.cloud.restrict(
                username=user_info["name"],
                tenant_name=tenant_info["name"],
                password="default")
        else:
            restrict_cloud = self.cloud.restrict(
                tenant_name=tenant_info["name"])
        try:
            volume = restrict_cloud.cinder.volumes.create(
                volume_info["size"],
                display_name=volume_info["display_name"],
                display_description=volume_info["display_description"],
                imageRef=image_id)
        except Exception as exc:
            LOG.exception("Cannot create: %s", volume_info)
            raise exc
        else:
            volume = utils.wait_for(volume.id,
                                    self.cloud.cinder.volumes.get,
                                    value="available",
                                    timeout=timeout,
                                    check_interval=3)
            self.create_volume_event(volume._info)
        return volume._info


class CreateVolumeClone(CreateVolumeTask):
    def execute(self, volume_info, timeout, **requires):
        try:
            volume = self.cloud.cinder.volumes.create(
                volume_info["size"], source_volid=volume_info["id"])
        except exceptions.cinder_excs.NotFound as exc:
            LOG.exception("Source volume not found: %s", volume_info)
            raise exc
        else:
            volume = utils.wait_for(volume.id, self.cloud.cinder.volumes.get,
                                    value='available', timeout=timeout,
                                    check_interval=3)
            self.create_volume_event(volume._info)
        return volume._info


class DeleteVolume(task.BaseCloudTask):

    def do_delete(self, volume_info):
        volume = self.cloud.cinder.volumes.get(volume_info["id"])
        try:
            self.cloud.cinder.volumes.delete(volume.id)
        except exceptions.cinder_excs.BadRequest as exc:
            LOG.exception("Cannot delete: %s", str(volume._info))
            raise exc
        else:
            volume = utils.wait_for(volume.id, self.cloud.cinder.volumes.get,
                                    stop_excs=(
                                        exceptions.cinder_excs.NotFound,))
            LOG.info("Deleted: %s", str(volume_info))
            self.delete_volume_event(volume_info)

    def execute(self, volume_info, **requires):
        self.do_delete(volume_info)

    def delete_volume_event(self, volume_info):
        events.emit("delete", {
            "cloud": self.cloud.name,
            "type": "volume",
            "id": volume_info["id"]
        }, namespace="/events")


class DeleteSourceVolume(DeleteVolume):
    def execute(self, volume_info):
        try:
            volume = self.cloud.cinder.volumes.get(volume_info["id"])

            # Also we need check 'delete resources from source cloud' option
            if not len(volume.attachments):
                self.do_delete(volume_info)

        except exceptions.cinder_excs.NotFound as exc:
            LOG.info("Volume: %s allready deleted before", str(volume_info))
            pass


class BlockDeviceMapping(Task):
    def execute(self, volume_src, volume_dst, server_id):
        dev_mapping = volume_dst["id"]
        attachments = volume_src["attachments"]
        for attachment in attachments:
            if attachment["server_id"] == server_id:
                dev_name = attachment["device"]
        return (str(dev_name), str(dev_mapping))


def migrate_detached_volume(context, volume_id, user_id, tenant_id):
    volume_binding = "volume-{}".format(volume_id)
    volume_retrieve = "{}-retrieve".format(volume_binding)
    volume_upload = "{}-upload".format(volume_binding)
    image_ensure = "{}-image-ensure".format(volume_binding)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    if user_id:
        user_ensure = "user-{}-ensure".format(user_id)
    else:
        user_ensure = "user-none-ensure"
        context.store[user_ensure] = None
    volume_ensure = "{}-ensure".format(volume_binding)
    timeout = context.config.get("volume_tasks_timeout", 120)

    flow = graph_flow.Flow("migrate-{}".format(volume_binding))
    flow.add(RetrieveVolume(context.src_cloud,
                            name=volume_binding,
                            provides=volume_binding,
                            rebind=[volume_retrieve]))
    flow.add(UploadVolume(context.src_cloud,
                          name=volume_upload,
                          provides=volume_upload,
                          rebind=[volume_binding],
                          inject={"timeout": int(timeout)})),
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
                                           image_ensure,
                                           user_ensure,
                                           tenant_ensure],
                                   inject={"timeout": int(timeout)})),
    context.store[volume_retrieve] = volume_id
    return flow


def migrate_attached_volume(context, server_id, volume_id,
                            user_id, tenant_id):
    volume_binding = "volume-{}".format(volume_id)
    volume_retrieve = "{}-retrieve".format(volume_binding)
    volume_clone = "{}-clone".format(volume_binding)
    volume_image = "{}-image".format(volume_binding)
    volume_ensure = "{}-ensure".format(volume_binding)
    volume_delete = "{}-delete".format(volume_binding)
    volume_mapping = "{}-mapping".format(volume_binding)
    image_ensure = "{}-image-ensure".format(volume_binding)
    server_binding = "server-{}".format(server_id)
    server_retrieve = "{}-retrieve".format(server_binding)
    server_suspend = "{}-suspend".format(server_binding)
    volume_sync = "{}-sync".format(volume_binding)
    user_ensure = "user-{}-ensure".format(user_id)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    timeout = context.config.get("volume_tasks_timeout", 120)

    flow = graph_flow.Flow("migrate-{}".format(volume_binding))
    flow.add(RetrieveVolume(context.src_cloud,
                            name=volume_binding,
                            provides=volume_binding,
                            rebind=[volume_retrieve]),
             CreateVolumeClone(context.src_cloud,
                               name=volume_clone,
                               provides=volume_clone,
                               rebind=[volume_binding],
                               requires=[server_suspend],
                               inject={"timeout": int(timeout)}),
             UploadVolume(context.src_cloud,
                          name=volume_image,
                          provides=volume_image,
                          rebind=[volume_clone],
                          inject={"timeout": int(timeout)}),
             image_tasks.EnsureSingleImage(context.src_cloud,
                                           context.dst_cloud,
                                           name=image_ensure,
                                           provides=image_ensure,
                                           rebind=[volume_image,
                                                   user_ensure]),
             CreateVolumeFromImage(context.dst_cloud,
                                   name=volume_ensure,
                                   provides=volume_ensure,
                                   rebind=[volume_binding,
                                           image_ensure,
                                           user_ensure,
                                           tenant_ensure],
                                   inject={"timeout": int(timeout)}),
             DeleteVolume(context.src_cloud,
                          name=volume_delete,
                          rebind=[volume_clone],
                          requires=[volume_ensure]),
             BlockDeviceMapping(name=volume_mapping,
                                provides=volume_mapping,
                                rebind=[volume_binding,
                                        volume_ensure,
                                        server_retrieve]))
    context.store[volume_retrieve] = volume_id
    return flow


def migrate_server_volumes(context, server_id, attachments,
                           user_id, tenant_id):
    server_block_devices = []
    flow = graph_flow.Flow("migrate-server-{}-volumes".format(server_id))
    for attachment in attachments:
        volume_id = attachment["id"]
        volume_retrieve = "volume-{}-retrieve".format(volume_id)
        if volume_retrieve not in context.store:
            server_block_devices.append("volume-{}-mapping".format(volume_id))
            volume_flow = migrate_attached_volume(context,
                                                  server_id,
                                                  volume_id,
                                                  user_id,
                                                  tenant_id)
            flow.add(volume_flow)

    server_device_mapping = "server-{}-device-mapping".format(server_id)
    flow.add(utils_tasks.Gather(name=server_device_mapping,
                                provides=server_device_mapping,
                                requires=server_block_devices))

    return flow
