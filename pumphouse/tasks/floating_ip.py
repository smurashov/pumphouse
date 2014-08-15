import logging

from taskflow.patterns import linear_flow

from pumphouse import tasks
from pumphouse import exceptions


LOG = logging.getLogger(__name__)


class RetrieveFloatingIP(tasks.BaseRetrieveTask):
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
                raise  # TODO(ogelbukh): emit event here
            else:
                LOG.info("Created: %s", floating_ip._info)
                pass  # TODO(ogelbukh): emit event here
        else:
            LOG.warn("Already exists, %s", floating_ip._info)
            pass  # TODO(ogelbukh): emit event here
        return floating_ip.to_dict()


class EnsureFloatingIP(tasks.BaseCloudTask):
    def execute(self, server_info, floating_ip_info, fixed_ip_info=dict()):
        floating_ip_address = floating_ip_info["address"]
        fixed_ip_address = fixed_ip_info.get("address")
        pool = floating_ip_info["pool"]
        server_id = server_info["id"]
        floating_ip = self.cloud.nova.floating_ip_bulk.find(
            address=floating_ip_address)
        if floating_ip["instance_uuid"] is None:
            try:
                self.cloud.nova.servers.add_floating_ip(
                    server_id, floating_ip_address, fixed_ip_address)
            except exceptions.nova_excs.NotFound:
                LOG.exception("No Floating IP: %s", floating_ip_info)
                raise
            else:
                floating_ip = self.cloud.nova.floating_ips.get(
                    floating_ip_address)
                return floating_ip.to_dict()
        elif floating_ip["instance_uuid"] == server_id:
            LOG.warn("Already associated: %s", floating_ip)
            return floating_ip.to_dict()
        else:
            # TODO(ogelbukh) raise native pumphouse exception here
            LOG.exception("Duplicate association: %s", floating_ip)
            raise exceptions.nova_excs.Conflict()


def migrate_floating_ip(src, dst, store, address):
    """Replicate Floating IP from source cloud to destination cloud"""
    floating_ip_binding = "floating-ip-{}".format(address)
    floating_ip_retrieve = "floating-ip-{}-retrieve".format(address)
    floating_ip_bulk_ensure = "floating-ip-bulk-{}-ensure".format(address)
    flow = linear_flow.Flow("migrate-floating-ip-{}".format(address))
    flow.add(tasks.RetrieveFloatingIP(src,
                                      name=floating_ip_retrieve,
                                      provides=floating_ip_retrieve,
                                      requires=[floating_ip_binding]))
    flow.add(tasks.EnsureFloatingIPBulk(dst,
                                        name=floating_ip_bulk_ensure,
                                        provides=floating_ip_bulk_ensure,
                                        requires=[floating_ip_retrieve]))
    store[floating_ip_binding] = address
    return flow, store


def associate_floating_ip_server(src, dst, store, floating_ip_address,
                                 fixed_ip_address, server_id):
    """Associates Floating IP to Nova instance"""
    floating_ip_binding = "floating-ip-{}".format(floating_ip_address)
    fixed_ip_binding = "fixed-ip-{}".format(server_id)
    server_ensure = "server-{}-ensure".format(server_id)
    floating_ip_ensure = "flotaing-ip-{}-ensure".format(floating_ip_address)
    flow = linear_flow.Flow("associate-floating-ip-{}-server-{}"
                            .format(floating_ip_address, server_id))
    flow.add(tasks.EnsureFloatingIP(dst,
                                    name=floating_ip_binding,
                                    provides=floating_ip_ensure,
                                    requires=[server_ensure,
                                              floating_ip_binding]))
    return flow, store
