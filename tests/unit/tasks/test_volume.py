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
from mock import Mock, MagicMock, patch, call

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
            "os-vol-tenant-attr:tenant_id": "456",
        }
        self.image_info = {
            "id": self.test_image_id,
            "name": "testvol1-image",
            "status": "active",
        }
        self.user_info = {
            "id": "345",
            "name": "test-user-name",
        }
        self.tenant_info = {
            "id": "456",
            "name": "test-tenant-name",
        }
        self.upload_info = {
            "id": self.test_volume_id,
            "os-volume_upload_image": {
                "image_id": self.test_image_id,
            }
        }
        self.snapshot_info = {
            "id": "567",
            "status": "available",
            "volume_id": self.test_volume_id
        }

        self.volume = Mock()
        self.volume.id = self.test_volume_id
        self.volume.status = "available"
        self.volume._info = self.volume_info

        self.image = MagicMock(**self.image_info)
        self.image.__getitem__.side_effect = self.image_info.__getitem__
        self.image.keys.side_effect = self.image_info.keys

        self.snapshot = Mock()
        self.snapshot.id = "567"
        self.snapshot.status = "available"
        self.snapshot._info = self.snapshot_info

        self.resp = Mock()
        self.resp.ok = True
        self.resp.reason = "Accepted"

        self.cloud = Mock()
        self.cloud.name = "test_cloud"
        self.cloud.cinder.volumes.get.return_value = self.volume
        self.cloud.cinder.volumes.upload_to_image.return_value = (
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
        self.cloud.cinder.volumes.upload_to_image.assert_called_once_with(
            self.test_volume_id,
            False,
            "pumphouse-volume-{}-image".format(self.volume_info["id"]),
            'bare',
            'raw')
        self.assertEqual(len(self.cloud.glance.images.get.call_args), 2)
        self.assertEqual(self.test_image_id, image_id)
        upload_volume.upload_to_glance_event.assert_called_once_with(
            self.image_info)

    def test_execute_bad_request(self):
        upload_volume = volume.UploadVolume(self.cloud)
        self.cloud.cinder.volumes.upload_to_image.side_effect = \
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
        self.cloud.restrict.return_value = self.cloud
        create_volume_dict = {
            "display_name": self.volume_info["display_name"],
            "display_description": self.volume_info["display_description"],
            "imageRef": self.test_image_id,
        }

        volume_info = create_volume.execute(self.volume_info,
                                            self.image_info,
                                            self.user_info,
                                            self.tenant_info)
        self.cloud.cinder.volumes.create.assert_called_once_with(
            self.volume_info["size"], **create_volume_dict)
        self.assertEqual(len(self.cloud.cinder.volumes.get.call_args), 2)
        self.assertEqual(self.volume_info, volume_info)

    def test_execute_bad_request(self):
        create_volume = volume.CreateVolumeFromImage(self.cloud)
        self.cloud.restrict.return_value = self.cloud
        self.cloud.cinder.volumes.create.side_effect = \
            exceptions.cinder_excs.BadRequest("400 Bad Request")

        with self.assertRaises(exceptions.cinder_excs.BadRequest):
            create_volume.execute(self.volume_info,
                                  self.image_info,
                                  self.user_info,
                                  self.tenant_info)


class TestCreateVolumeSnapshot(TestVolume):
    def test_execute(self):
        create_volume = volume.CreateVolumeSnapshot(self.cloud)
        self.cloud.cinder.volume_snapshots.create.return_value = self.snapshot
        self.cloud.cinder.volume_snapshots.get.return_value = self.snapshot

        snapshot_info = create_volume.execute(self.volume_info)
        self.assertIsInstance(create_volume, task.BaseCloudTask)
        self.cloud.cinder.volume_snapshots.create.assume_called_once_with(
            self.test_volume_id)
        self.assertEqual(snapshot_info, self.snapshot_info)


class TestCreateVolumeClone(TestVolume):
    def test_execute(self):
        self.volume_info.update({"source_volid": self.test_volume_id})
        create_volume = volume.CreateVolumeClone(self.cloud)

        volume_info = create_volume.execute(self.volume_info)
        self.assertIsInstance(create_volume, task.BaseCloudTask)
        self.cloud.cinder.volumes.create.assert_called_once_with(
            self.volume_info["size"],
            source_volid=self.test_volume_id)
        self.assertEqual(volume_info, self.volume_info)


class TestDeleteVolume(TestVolume):
    def test_do_delete(self):
        delete_volume = volume.DeleteVolume(self.cloud)


class TestCreateVolumeTask(TestVolume):
    @patch("pumphouse.events.emit")
    def test_create_volume_event(self, mock_emit):
        expected_dict = {
            "cloud": self.cloud.name,
            "id": self.test_volume_id,
            "status": "active",
            "name": self.volume_info["display_name"],
            "tenant_id": self.volume_info["os-vol-tenant-attr:tenant_id"],
            "host_id": None,
            "server_ids": []
        }

        class TestCreateVolumeClass(volume.CreateVolumeTask):
            def execute(self):
                pass

        create_volume = TestCreateVolumeClass(self.cloud)
        create_volume.create_volume_event(self.volume_info)

        self.assertIsInstance(create_volume, volume.CreateVolumeTask)
        self.assertIsInstance(create_volume, task.BaseCloudTask)
        mock_emit.assume_called_once_with("volume create",
                                          expected_dict,
                                          namespace="/events")


class TestMigrateVolume(TestVolume):
    def setUp(self):
        super(TestMigrateVolume, self).setUp()
        self.volume_binding = "volume-{}".format(self.test_volume_id)
        self.volume_retrieve = "{}-retrieve".format(self.volume_binding)
        self.volume_upload = "{}-upload".format(self.volume_binding)
        self.image_ensure = "{}-image-ensure".format(self.volume_binding)
        self.user_id = "none"
        self.user_ensure = "user-{}-ensure".format(self.user_id)
        self.volume_ensure = "{}-ensure".format(self.volume_binding)


class TestMigrateDetachedVolume(TestMigrateVolume):
    @patch("pumphouse.tasks.image.EnsureSingleImage")
    @patch.object(volume, "CreateVolumeFromImage")
    @patch.object(volume, "UploadVolume")
    @patch.object(volume, "RetrieveVolume")
    @patch("taskflow.patterns.graph_flow.Flow")
    def test_migrate_detached_volume(self, flow_mock,
                                     retrieve_vol_mock,
                                     upload_vol_mock,
                                     create_vol_mock,
                                     ensure_img_mock):
        expected_store_dict = {self.volume_retrieve: self.test_volume_id,
                               self.user_ensure: None}
        flow = volume.migrate_detached_volume(self.context,
                                              self.test_volume_id)

        retrieve_vol_mock.assert_called_once_with(
            self.context.src_cloud, name=self.volume_binding,
            provides=self.volume_binding, rebind=[self.volume_retrieve])
        upload_vol_mock.assert_called_once_with(
            self.context.src_cloud, name=self.volume_upload,
            provides=self.volume_upload, rebind=[self.volume_binding])
        create_vol_mock.assert_called_once_with(
            self.context.dst_cloud, name=self.volume_ensure,
            provides=self.volume_ensure,
            rebind=[self.volume_binding, self.image_ensure])
        ensure_img_mock.assert_called_once_with(
            self.context.src_cloud, self.context.dst_cloud,
            name=self.image_ensure, provides=self.image_ensure,
            rebind=[self.volume_upload, self.user_ensure])
        flow_mock.assert_called_once_with(
            "migrate-{}".format(self.volume_binding))
        self.assertEqual(self.context.store, expected_store_dict)
        self.assertEqual(flow.add.call_args_list,
                         [call(retrieve_vol_mock()),
                          call(upload_vol_mock()),
                          call(ensure_img_mock()),
                          call(create_vol_mock())])


class TestMigrateAttachedVolume(TestMigrateVolume):
    def setUp(self):
        super(TestMigrateVolume, self).setUp()
        self.test_server_id = "456"

    def test_migrate_attached_volume(self):
        flow = volume.migrate_attached_volume(self.context,
                                              self.test_server_id,
                                              self.test_volume_id,
                                              self.user_info,
                                              self.tenant_info)
