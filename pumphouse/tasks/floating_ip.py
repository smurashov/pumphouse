import logging

from taskflow.patterns import linear_flow

from pumphouse import tasks
from pumphouse import exceptions
from pumphoust import utils


LOG = logging.getLogger(__name__)


class RetrieveFixedIP(tasks.BaseRetriveTask):
    def retrieve(self, server_id, network_id):
        server = self.cloud.nova.servers.get(server_id)
        # XXX(ogelbukh): this is only for nova-network with FlatDHCP
        network = self.cloud.nova.networks.find(project_id=None)
        fixed_ip_address = server.get("addresses")[network.label][0]["addr"]
        return fixed_ip_address


class RetrieveFloatingIPBulk(tasks.BaseRetrieveTask):
    def retrieve(self, address):
        floating_ip = self.cloud.nova.floating_ips_bulk.find(address=address)
        return floating_ip.to_dict()


class EnsureFloatingIPBulk(tasks.BaseCloudTask):
    def execute(self, floating_ip_info):
        address = floating_ip_info["addr"]
        pool = floating_ip_info["pool"]
        try:
            floating_ip = self.cloud.nova.floating_ips_bulk.find(
                address=address)
        except exceptions.nova_excs.NotFound:
            self.cloud.nova.floating_ips_bulk.create(address,
                                                pool=pool)
            try:
                floating_ip = self.cloud.nova.floating_ips_bulk.find(
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


class EnsureFloatingIP(tasks.BaseCloudTask):
    def execute(self, server_info, floating_ip_info, fixed_ip):
        pool = floating_ip_info.get("pool")
        server_id = server_info.get("id")
        try:
            floating_ip = self.cloud.nova.floating_ips.create(pool=pool)
        except exceptions.nova_excs.NotFound:
            LOG.exception("No floating ip available")
            raise
        else:
            floating_ip = utils.wait_for(
                (floating_ip, server_id, fixed_ip),
                self._associate_floating_ip,
                attribute_getter=self._get_floating_ip_server,
                value=server_id)
        return floating_ip

    def _associate_floating_ip(self, (floating_ip, server_id, fixed_ip)):
        try:
            self.cloud.nova.servers.add_floating_ip(
                server_id, floating_ip.ip, fixed_ip)
        except exceptions.nova_excs.BadRequest:
            return floating_ip
        else:
            return self.cloud.nova.floating_ips.get(floating_ip),

    def _get_floating_ip_server(floating_ip):
        return floating_ip.instance_id


def migrate_floating_ip(src, dst, store, address):
    floating_ip_bulk_binding = "floating-ip-bulk-{}".format(address)
    floating_ip_bulk_retrieve = "floating-ip-bulk-{}-retrieve".format(address)
    floating_ip_bulk_ensure = "floating-ip-bulk-{}-ensure".format(address)
    flow = linear_flow.Flow("migrate-floating-ip-{}".format(address))
    flow.add(tasks.RetrieveFloatingIPBulk(src,
                                          name=floating_ip_bulk_retrieve,
                                          provides=floating_ip_bulk_retrieve,
                                          requires=[floating_ip_bulk_binding]))
    flow.add(tasks.EnsureFloatingIPBulk(dst,
                                        name=floating_ip_bulk_ensure,
                                        provides=floating_ip_bulk_ensure,
                                        requires=[floating_ip_bulk_retrieve]))
    store[floating_ip_bulk_binding] = address
    return flow, store


def assign_floating_ip(src, dst, store, floating_ip_address,
                       fixed_ip_address, server_id):
    floating_ip_binding = "floating-ip-{}".format(floating_ip_address)
    fixed_ip_binding = "fixed-ip-{}".format(server_id)
    server_ensure = "server-{}-ensure".format(server_id)
    floating_ip_ensure = "flotaing-ip-{}-ensure".format(floating_ip_address)
    flow = linear_flow.Flow("assign-floating-ip-{}-server-{}"
                            .format(floating_ip_address, server_id))
    flow.add(tasks.RetrieveFixedIP(src,
                                   name=fixed_ip_binding,
                                   provides=fixed_ip_binding,
                                   requires=[server_ensure]))
    flow.add(tasks.EnsureFloatingIP(dst,
                                    name=floating_ip_binding,
                                    provides=floating_ip_ensure,
                                    requires=[server_ensure,
                                              floating_ip_binding,
                                              fixed_ip_binding]))
    store[floating_ip_binding] = floating_ip_address
    return flow, store
