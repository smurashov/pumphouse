import logging

from taskflow import task

from pumphouse import exceptions
from pumphoust import utils


LOG = logging.getLogger(__name__)


class RetrieveFloatingIPBulk(BaseRetrieveTask):
    def retrieve(self, address):
        floating_ip = cloud.nova.floating_ips_bulk.find(address=address)
        return floating_ip


class EnsureFloatingIPBulk(BaseCloudTask):
    def execute(self, floating_ip_info):
        address = floating_ip_info.get("addr")
        pool = floating_ip_info.get("pool")
        try:
            floating_ip = cloud.nova.floating_ips_bulk.find(
                address=address)
        except exceptions.nova_excs.NotFound:
            cloud.nova.floating_ips_bulk.create(address,
                                                pool=pool)
            try:
                floating_ip = cloud.nova.floating_ips_bulk.find(
                    address=address)
            except exceptions.nova_excs.NotFound:
                LOG.exception("Not added: %s", address)
                raise # TODO(ogelbukh): emit event here
            else:
                LOG.info("Created: %s", floating_ip._info)
                pass  # TODO(ogelbukh): emit event here
        else:
            LOG.warn("Already exists, %s", floating_ip._info)
            pass  # TODO(ogelbukh): emit event here
        return floating_ip


class EnsureFloatingIP(BaseCloudTask):
    def execute(self, server_info, floating_ip_info, fixed_ip):
        pool = floating_ip_info.get("pool")
        server_id = server_info.get("id")
        try:
            floating_ip = cloud.nova.floating_ips.create(pool=pool)
        except exceptions.nova_excs.NotFound:
            LOG.exception("No floating ip available")
            raise
        else:
            floating_ip = utils.wait_for(
                (floating_ip, server_id, fixed_ip),
                self._associate_floating_ip,
                attribute_getter=self._get_floating_ip_server,
                value=server.id)

    def _associate_floating_ip(self, (floating_ip, server_id, fixed_ip)):
        try:
            self.cloud.nova.servers.add_floating_ip(
                server_id, floating_ip.ip, fixed_ip)
        except nova_excs.BadRequest:
            return floating_ip
        else:
            return self.cloud.nova.floating_ips.get(floating_ip),

    def _get_floating_ip_server(floating_ip):
        return floating_ip.instance_id


def migrate_floating_ip(src, dst, store, address, server_id):
    floating_ip_binding = "floating-ip-{}".format(address)
    floating_ip_bulk_retrieve = "floating-ip-bulk-{}-retrieve".format(address)
    floating_ip_bulk_ensure = "floating-ip-bulk-{}-ensure".format(address)
    floating_ip_ensure = "flotaing-ip-{}-ensure".format(address)
    server_ensure = "server-{}-ensure".format(server_id)
    flow = linear_flow.Flow("migrate-floating-ip-{}".format(address))
    flow.add(tasks.RetrieveFloatingIPBulk(src,
                                          name=floating_ip_bulk_retrieve,
                                          provides=floating_ip_bulk_retrieve,
                                          requires=[floating_ip_binding]))
    flow.add(tasks.EnsureFloatingIPBulk(dst,
                                        name=floating_ip_bulk_ensure
                                        provides=floating_ip_bulk_ensure,
                                        requires=[floating_ip_bulk_retrieve]))
    flow.add(tasks.EnsureFloatingIP(dst,
                                    name=floating_ip_ensure,
                                    provides=floating_ip_ensure,
                                    requires=[floating_ip_bulk_ensure,
                                              server_ensure]))
    store[flavor_ip_binding] = address
