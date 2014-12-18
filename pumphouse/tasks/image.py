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

import itertools
import logging

from taskflow.patterns import graph_flow

from pumphouse import task
from pumphouse import events
from pumphouse import exceptions
from pumphouse.tasks import utils as task_utils


LOG = logging.getLogger(__name__)


class LogReporter(task_utils.UploadReporter):
    def report(self, absolute):
        cloud_name, src_image, dst_image = self.context
        LOG.info("Image %r uploaded on %3.2f%%",
                 dst_image["id"], absolute * 100)
        events.emit("update", {
            "id": dst_image["id"],
            "type": "image",
            "cloud": cloud_name,
            "action": None,
            "progress": round(absolute * 100),
            "data": dict(dst_image),
        }, namespace="/events")


class EnsureImage(task.BaseCloudsTask):
    def execute(self, image_id, tenant_info, kernel_info, ramdisk_info):
        if tenant_info:
            tenant = self.dst_cloud.keystone.tenants.get(tenant_info["id"])
            dst_cloud = self.dst_cloud.restrict(tenant_name=tenant.name)
        else:
            dst_cloud = self.dst_cloud
        image_info = self.src_cloud.glance.images.get(image_id)
        images = self.dst_cloud.glance.images.list(filters={
            # FIXME(akscram): Not all images have the checksum property.
            "checksum": image_info["checksum"],
            "name": image_info["name"],
        })
        try:
            # XXX(akscram): More then one images can be here. Now we
            #               just ignore this fact.
            image = next(iter(images))
        except StopIteration:
            parameters = {
                "disk_format": image_info["disk_format"],
                "container_format": image_info["container_format"],
                "visibility": image_info["visibility"],
                "min_ram": image_info["min_ram"],
                "min_disk": image_info["min_disk"],
                "name": image_info["name"],
                "protected": image_info["protected"],
            }
            if kernel_info:
                parameters["kernel_id"] = kernel_info["id"]
            if ramdisk_info:
                parameters["ramdisk_id"] = ramdisk_info["id"]
            # TODO(akscram): Some image can contain additional
            #                parameters which are skipped now.
            image = dst_cloud.glance.images.create(**parameters)
            self.created_event(image)

            data = self.src_cloud.glance.images.data(image_info["id"])
            img_data = task_utils.FileProxy(data, image_info["size"],
                                            LogReporter((dst_cloud.name,
                                                         image_info,
                                                         image)))
            dst_cloud.glance.images.upload(image["id"], img_data)
            image = dst_cloud.glance.images.get(image["id"])
            self.uploaded_event(image)
        return dict(image)

    def created_event(self, image):
        LOG.info("Image created: %s", image["id"])
        events.emit("create", {
            "id": image["id"],
            "type": "image",
            "cloud": self.dst_cloud.name,
            "action": "uploading",
            "data": dict(image),
        }, namespace="/events")

    def uploaded_event(self, image):
        LOG.info("Image uploaded: %s", image["id"])
        events.emit("update", {
            "id": image["id"],
            "type": "image",
            "cloud": self.dst_cloud.name,
            "progress": None,
            "action": None,
            "data": dict(image),
        }, namespace="/events")


class EnsureImageWithKernel(EnsureImage):
    def execute(self, image_id, user_info, kernel_info):
        return super(EnsureSingleImage, self).execute(image_id, user_info,
                                                      kernel_info, None)


class EnsureImageWithRamdisk(EnsureImage):
    def execute(self, image_id, user_info, ramdisk_info):
        return super(EnsureSingleImage, self).execute(image_id, user_info,
                                                      None, ramdisk_info)


class EnsureSingleImage(EnsureImage):
    def execute(self, image_id, user_info):
        return super(EnsureSingleImage, self).execute(image_id, user_info,
                                                      None, None)


class DeleteImage(task.BaseCloudTask):
    def execute(self, image_info, **requires):
        image_id = image_info["id"]
        try:
            self.cloud.glance.images.delete(image_id)
        except exceptions.glance_excs.BadRequest as exc:
            LOG.exception("Error deleting: %s", str(image_info))
            raise exc
        else:
            LOG.info("Deleted: %s", str(image_info))
            self.delete_event(image_info)

    def delete_event(self, image_info):
        events.emit("delete", {
            "cloud": self.cloud.name,
            "type": "image",
            "id": image_info["id"]
        }, namespace="/events")


class DeleteImageByID(DeleteImage):
    def execute(self, image_id, **requires):
        image = self.cloud.glance.images.get(image_id)
        super(DeleteImageByID, self).execute(dict(image))


def migrate_image_task(context, task_class, image_id, tenant_id, *rebind):
    image_binding = "image-{}".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)
    tenant_ensure = "tenant-{}-ensure".format(tenant_id)
    rebind = itertools.chain((image_binding, tenant_ensure), *rebind)
    task = task_class(context.src_cloud, context.dst_cloud,
                      name=image_ensure,
                      provides=image_ensure,
                      rebind=list(rebind))
    context.store[image_binding] = image_id
    return task


# XXX(akscram): We should to simplify this function. The cascade of
#               if-statements looks ugly.
def migrate_image(context, image_id):
    image = context.src_cloud.glance.images.get(image_id)
    tenant_id = None
    if image["visibility"] == "private":
        tenant_id = image.get("owner")
    else:
        tenant_ensure = "image-{}-ensure".format("public")
        context.store[tenant_ensure] = None
    if image["container_format"] == "ami" and (hasattr(image, "kernel_id") or
                                               hasattr(image, "ramdisk_id")):
        flow = graph_flow.Flow("migrate-image-{}".format(image_id))
        if hasattr(image, "kernel_id") and hasattr(image, "ramdisk_id"):
            kernel = migrate_image_task(context, EnsureSingleImage,
                                        image["kernel_id"], tenant_id)
            ramdisk = migrate_image_task(context, EnsureSingleImage,
                                         image["ramdisk_id"], tenant_id)
            image = migrate_image_task(context, EnsureImage, image_id,
                                       tenant_id, kernel.provides,
                                       ramdisk.provides)
            flow.add(kernel, ramdisk, image)
        elif hasattr(image, "kernel_id"):
            kernel = migrate_image_task(context, EnsureSingleImage,
                                        image["kernel_id"], tenant_id)
            image = migrate_image_task(context, EnsureImageWithKernel,
                                       image_id, tenant_id, kernel.provides)
            flow.add(kernel, image)
        else:
            ramdisk = migrate_image_task(context, EnsureSingleImage,
                                         image["ramdisk_id"], tenant_id)
            image = migrate_image_task(context, EnsureImageWithRamdisk,
                                       image_id, tenant_id, ramdisk.provides)
            flow.add(ramdisk, image)
    else:
        flow = migrate_image_task(context, EnsureSingleImage,
                                  image_id, tenant_id)
    return flow
