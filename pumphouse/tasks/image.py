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


LOG = logging.getLogger(__name__)


class EnsureImage(task.BaseCloudsTask):
    def execute(self, image_id, kernel_info, ramdisk_info):
        image_info = self.src_cloud.glance.images.get(image_id)
        images = self.dst_cloud.glances.images.list(filters={
            # FIXME(akscram): Not all images have the checksum property.
            "checksum": image_info["checksum"],
            "name": image_info["name"],
        })
        try:
            # XXX(akscram): More then one images can be here. Now we
            #               just ignore this fact.
            image = next(iter(images))
        except StopIteration:
            image = self.dst_cloud.glances.images.create(
                disk_format=image_info["disk_format"],
                container_format=image_info["container_format"],
                visibility=image_info["visibility"],
                min_ram=image_info["min_ram"],
                min_disk=image_info["min_disk"],
                name=image_info["name"],
                protected=image_info["protected"],
                kernel_id=kernel_info["id"] if kernel_info else None,
                ramdisk_id=ramdisk_info["id"] if ramdisk_info else None,
            )
            # TODO(akscram): Chunked request is preferred. So in the
            #                future we can control this for generating
            #                the progress of the upload.
            data = self.src_cloud.glance.images.data(image_info["id"])
            self.dst_cloud.glance.images.upload(image["id"], data._resp)
        return dict(image)


def migrate_image(src, dst, store, image_id):
    image_retrieve = "image-{}-retrieve".format(image_id)
    image_ensure = "image-{}-ensure".format(image_id)
    requires, inject = [image_retrieve], {}
    image = src.glance.images.get(image_id)
    flow = graph_flow.Flow("migrate-image-{}".format(image_id))
    if hasattr(image, "kernel_id"):
        kernel_retrieve = "image-{}-retrieve".format(image["kernel_id"])
        kernel_ensure = "image-{}-ensure".format(image["kernel_id"])
        flow.add(EnsureImage(src, dst,
                             name=kernel_ensure,
                             provides=kernel_ensure,
                             requires=(kernel_retrieve,),
                             inject={"kernel_id": None,
                                     "ramdisk_id": None}))
        store[kernel_retrieve] = image["kernel_id"]
        requires.append(kernel_ensure)
    else:
        inject["kernel_id"] = None
    if hasattr(image, "ramdisk_id"):
        ramdisk_retrieve = "image-{}-retrieve".format(image["ramdisk_id"])
        ramdisk_ensure = "image-{}-ensure".format(image["ramdisk_id"])
        flow.add(EnsureImage(src, dst,
                             name=ramdisk_ensure,
                             provides=ramdisk_ensure,
                             requires=(ramdisk_retrieve,),
                             inject={"kernel_id": None,
                                     "ramdisk_id": None}))
        store[ramdisk_retrieve] = image["ramdisk_id"]
        requires.append(ramdisk_ensure)
    else:
        inject["ramdisk_id"] = None
    flow.add(EnsureImage(src, dst,
                         name=image_ensure,
                         provides=image_ensure,
                         inject=inject,
                         requires=requires))
    store[image_retrieve] = image_id
    return (flow, store)
