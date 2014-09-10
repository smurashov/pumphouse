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
from pumphouse.tasks import utils as task_utils


LOG = logging.getLogger(__name__)


class LogReporter(task_utils.UploadReporter):
    def report(self, absolute):
        LOG.info("Image %r uploaded on %3.2f%%",
                 self.context["id"], absolute * 100)
        events.emit("image uploading", {
            "id": self.context["id"],
            "progress": round(absolute * 100)
        }, namespace="/events")


class EnsureImage(task.BaseCloudsTask):
    def execute(self, image_id, kernel_info, ramdisk_info):
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
            image = self.dst_cloud.glance.images.create(**parameters)
            self.created_event(image)

            data = self.src_cloud.glance.images.data(image_info["id"])
            img_data = task_utils.FileProxy(data, LogReporter(image))
            self.dst_cloud.glance.images.upload(image["id"], img_data)
            image = self.dst_cloud.glance.images.get(image["id"])
            self.uploaded_event(image)
        return dict(image)

    def created_event(self, image):
        LOG.info("Image created: %s", image["id"])
        events.emit("image created", {
            "id": image["id"],
            "name": image["name"],
            "cloud": self.dst_cloud.name
        }, namespace="/events")

    def uploaded_event(self, image):
        LOG.info("Image uploaded: %s", image["id"])
        events.emit("image uploaded", {
            "id": image["id"]
        }, namespace="/events")


class EnsureImageWithKernel(EnsureImage):
    def execute(self, image_id, kernel_info):
        return super(EnsureSingleImage, self).execute(image_id, kernel_info,
                                                      None)


class EnsureImageWithRamdisk(EnsureImage):
    def execute(self, image_id, ramdisk_info):
        return super(EnsureSingleImage, self).execute(image_id, None,
                                                      ramdisk_info)


class EnsureSingleImage(EnsureImage):
    def execute(self, image_id):
        return super(EnsureSingleImage, self).execute(image_id, None, None)


def migrate_image_task(src, dst, store, task_class, image_id, *rebind):
    image_retrieve = "image-{}-retrieve".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)
    rebind = set((image_retrieve,)).union(*rebind)
    task = task_class(src, dst,
                      name=image_ensure,
                      provides=image_ensure,
                      rebind=list(rebind))
    store[image_retrieve] = image_id
    return task, store


# XXX(akscram): We should to simplify this function. The cascade of
#               if-statements looks ugly.
def migrate_image(src, dst, store, image_id):
    image = src.glance.images.get(image_id)
    if image["container_format"] == "ami" and (hasattr(image, "kernel_id") or
                                               hasattr(image, "ramdisk_id")):
        flow = graph_flow.Flow("migrate-image-{}".format(image_id))
        if hasattr(image, "kernel_id") and hasattr(image, "ramdisk_id"):
            kernel, store = migrate_image_task(src, dst, EnsureSingleImage,
                                               store, image["kernel_id"])
            ramdisk, store = migrate_image_task(src, dst, EnsureSingleImage,
                                                store, image["ramdisk_id"])
            image, store = migrate_image_task(src, dst, EnsureImage, store,
                                              image_id, kernel.provides,
                                              ramdisk.provides)
            flow.add(kernel, ramdisk, image)
        elif hasattr(image, "kernel_id"):
            kernel, store = migrate_image_task(src, dst, EnsureSingleImage,
                                               store, image["kernel_id"])
            image, store = migrate_image_task(src, dst, EnsureImageWithKernel,
                                              store, image_id, kernel.provides)
            flow.add(kernel, image)
        else:
            ramdisk, store = migrate_image_task(src, dst, EnsureSingleImage,
                                                store, image["ramdisk_id"])
            image, store = migrate_image_task(src, dst, EnsureImageWithRamdisk,
                                              store, image_id,
                                              ramdisk.provides)
            flow.add(ramdisk, image)
    else:
        flow, store = migrate_image_task(src, dst, store, EnsureSingleImage,
                                         image_id)
    return flow, store