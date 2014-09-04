import unittest

from mock import Mock
from pumphouse import exceptions
from pumphouse import task
from pumphouse.tasks import floating_ip


class TestFloatingIP(unittest.TestCase):
    def setUp(self):
        self.test_address = "10.0.0.1"
        self.test_pool = "test-pool"
        self.test_instance_uuid = "123"

        self.floating_ip_info = {
            "address": self.test_address,
            "instance_uuid": self.test_instance_uuid,
            "pool": self.test_pool
        }
        self.fixed_ip_info = {
            "addr": self.test_address
        }
        self.server_info = {
            "id": "123"
        }
        self.floating_ip = Mock()
        self.floating_ip.instance_uuid = self.test_instance_uuid
        self.floating_ip.to_dict.return_value = self.floating_ip_info

        self.cloud = Mock()
        self.cloud.nova.floating_ips_bulk.find.return_value = self.floating_ip
        self.cloud.nova.servers.add_floating_ip.return_value = None

    def side_effect(self, *args, **kwargs):
        result = self.returns.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class TestRetrieveFloatingIP(TestFloatingIP):
    def test_execute(self):
        retrieve_floating_ip = floating_ip.RetrieveFloatingIP(self.cloud)
        self.assertIsInstance(retrieve_floating_ip, task.BaseCloudTask)

        retrieve_floating_ip.execute(self.test_address)
        self.cloud.nova.floating_ips_bulk.find.assert_called_once_with(
            address=self.test_address)


class TestEnsureFloatingIPBulk(TestFloatingIP):
    def test_execute(self):
        ensure_fip_bulk = floating_ip.EnsureFloatingIPBulk(
            self.cloud)
        self.assertIsInstance(ensure_fip_bulk, task.BaseCloudTask)

        fip = ensure_fip_bulk.execute(self.floating_ip_info)
        self.cloud.nova.floating_ips_bulk.find.assert_called_once_with(
            address=self.test_address)
        self.assertEquals(fip, self.floating_ip_info)

    def test_execute_not_found(self):
        ensure_fip_bulk = floating_ip.EnsureFloatingIPBulk(
            self.cloud)
        self.cloud.nova.floating_ips_bulk.find.side_effect = \
            [exceptions.nova_excs.NotFound(
                "404 Not Found"),
             self.floating_ip]

        ensure_fip_bulk.execute(self.floating_ip_info)
        self.assertEquals(
            self.cloud.nova.floating_ips_bulk.find.call_count, 2)
        self.cloud.nova.floating_ips_bulk.create.assert_called_once_with(
            self.test_address, pool=self.test_pool)

    def test_execute_not_created(self):
        ensure_fip_bulk = floating_ip.EnsureFloatingIPBulk(
            self.cloud)
        self.cloud.nova.floating_ips_bulk.find.side_effect = \
            exceptions.nova_excs.NotFound("404 Not Found")

        with self.assertRaises(exceptions.nova_excs.NotFound):
            ensure_fip_bulk.execute(self.floating_ip_info)
        self.assertEquals(
            self.cloud.nova.floating_ips_bulk.find.call_count, 2)


class TestEnsureFloatingIP(TestFloatingIP):
    def test_execute(self):
        ensure_floating_ip = floating_ip.EnsureFloatingIP(self.cloud)
        self.assertIsInstance(ensure_floating_ip, task.BaseCloudTask)

        fip = ensure_floating_ip.execute(self.server_info,
                                         self.test_address,
                                         self.fixed_ip_info)
        self.cloud.nova.floating_ips_bulk.assert_run_once_with(
            address=self.test_address)
        self.assertEquals(
            self.floating_ip_info, fip)

    def test_execute_not_found(self):
        ensure_floating_ip = floating_ip.EnsureFloatingIP(self.cloud)

        self.cloud.nova.floating_ips_bulk.find.side_effect = \
            exceptions.nova_excs.NotFound("404 Not Found")

        with self.assertRaises(exceptions.nova_excs.NotFound):
            ensure_floating_ip.execute(self.server_info,
                                       self.test_address,
                                       self.fixed_ip_info)

    def test_execute_add_floating_ip(self):
        ensure_floating_ip = floating_ip.EnsureFloatingIP(self.cloud)
        floating_ip_info_unassigned = self.floating_ip_info.copy()
        floating_ip_info_unassigned.update(instance_uuid=None)
        floating_ip_unassigned = Mock()
        floating_ip_unassigned.instance_uuid = None
        floating_ip_unassigned.to_dict.return_value = \
            floating_ip_info_unassigned
        self.returns = [floating_ip_unassigned,
                        self.floating_ip]
        self.cloud.nova.floating_ips_bulk.find.side_effect = \
            self.side_effect

        ensure_floating_ip.execute(self.server_info,
                                   self.test_address,
                                   self.fixed_ip_info)
        self.cloud.nova.servers.add_floating_ip.assert_run_once_with(
            self.test_instance_uuid, self.test_address, None)


if __name__ == '__main__':
    unittest.main()
