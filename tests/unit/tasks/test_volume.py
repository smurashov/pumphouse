# Copyright (c) 2014 mirantis inc.
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

import unittest
from mock import Mock

from pumphouse import task
from pumphouse.tasks import volume

from pumphouse import exceptions


class TestVolume(unittest.TestCase):
    def setUp(self):
        self.test_volume_id = "123"
        self.test_image_id = "234"
        self.volume_info = {
            "id": self.test_volume_id,
            "size": 1,
            "status": "available",
            "display_name": "testvol1",
            "display_description": None,
            "volume_type": "test_lvm",
        }
        self.image_info = {
            "id": self.test_image_id,
            "name": "testvol1-image",
            "status": "active",
        }
        self.user_info = {
            "id": "345",
        }
        self.upload_info = {
            "id": self.test_volume_id,
            "os-volume_upload_image": {
                "image_id": self.test_image_id,
            }
        }

        self.volume = Mock()
        self.volume.id = self.test_volume_id
        self.volume.status = "available"
        self.volume._info = self.volume_info

        self.image = Mock()
        self.image.id = self.test_image_id
        self.image.status = "active"
        self.image.to_dict.return_value = self.image_info

        self.resp = Mock()
        self.resp.ok = True
        self.resp.reason = "Accepted"

        self.cloud = Mock()
        self.cloud.name = "test_cloud"
        self.cloud.cinder.volumes.get.return_value = self.volume
        self.cloud.cinder.volumes.upload_to_glance.return_value = (
            self.resp,
            self.upload_info
        )
        self.cloud.cinder.volumes.create.return_value = self.volume
        self.cloud.glance.images.get.return_value = self.image

        self.src_cloud = Mock()
        self.dst_cloud = Mock()

        self.context = Mock()
        self.context.src_cloud = self.src_cloud
        self.context.dst_cloud = self.dst_cloud
        self.context.store = {}


class TestRetrieveVolume(TestVolume):
    def test_execute(self):
        retrieve_volume = volume.RetrieveVolume(self.cloud)
        self.assertIsInstance(retrieve_volume, task.BaseCloudTask)

        volume_info = retrieve_volume.execute(self.test_volume_id)
        self.cloud.cinder.volumes.get.assert_called_once_with(
            self.test_volume_id)
        self.assertEqual(self.volume_info, volume_info)


class TestUploadVolume(TestVolume):
    def test_execute(self):
        upload_volume = volume.UploadVolume(self.cloud)
        self.assertIsInstance(upload_volume, task.BaseCloudTask)
        upload_volume.upload_to_glance_event = Mock()

        image_id = upload_volume.execute(self.volume_info)
        self.cloud.cinder.volumes.upload_to_glance.assert_called_once_with(
            self.test_volume_id)
        self.assertEqual(len(self.cloud.glance.images.get.call_args), 2)
        self.assertEqual(self.test_image_id, image_id)
        upload_volume.upload_to_glance_event.assert_called_once_with(
            self.image_info)

    def test_execute_bad_request(self):
        upload_volume = volume.UploadVolume(self.cloud)
        self.cloud.cinder.volumes.upload_to_glance.side_effect = \
            exceptions.cinder_excs.BadRequest("400 Bad Request")

        with self.assertRaises(exceptions.cinder_excs.BadRequest):
            upload_volume.execute(self.volume_info)

    def test_execute_image_not_found(self):
        upload_volume = volume.UploadVolume(self.cloud)
        self.cloud.glance.images.get.side_effect = \
            exceptions.glance_excs.NotFound("404 Not Found")

        with self.assertRaises(exceptions.NotFound):
            upload_volume.execute(self.volume_info)


class TestCreateVolumeFromImage(TestVolume):
    def test_execute(self):
        create_volume = volume.CreateVolumeFromImage(self.cloud)
        self.assertIsInstance(create_volume, task.BaseCloudTask)
        create_volume.create_volume_event = Mock()
        create_volume_dict = {
            "display_name": self.volume_info["display_name"],
            "display_description": self.volume_info["display_description"],
            "volume_type": self.volume_info["volume_type"],
            "imageRef": self.test_image_id,
        }

        volume_info = create_volume.execute(self.volume_info,
                                            self.image_info)
        self.cloud.cinder.volumes.create.assert_called_once_with(
            self.volume_info["size"], **create_volume_dict)
        self.assertEqual(len(self.cloud.cinder.volumes.get.call_args), 2)
        self.assertEqual(self.volume_info, volume_info)

    def test_execute_bad_request(self):
        create_volume = volume.CreateVolumeFromImage(self.cloud)
        self.cloud.cinder.volumes.create.side_effect = \
            exceptions.cinder_excs.BadRequest("400 Bad Request")

        with self.assertRaises(exceptions.cinder_excs.BadRequest):
            create_volume.execute(self.volume_info,
                                  self.image_info)
