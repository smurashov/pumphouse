# FIXME(akscram): The version of client of Nova is hardcoded.
from novaclient.v1_1 import client as nova_client

from pumphouse import base


class NodeDiscovery(base.Discovery):

    def __init__(self):
        super(NodeDiscovery, self).__init__()
        service_type = 'compute'
        self.nova = nova_client.Client(self.username,
                                       self.password,
                                       self.tenant,
                                       self.auth_url,
                                       service_type)

    def discover(self):
        discovery = []
        nodes = nova_client.hypervisors.list()
        for node in nodes:
            discovery = discovery.append(
                             Node(node.id, node.hypervisor_hostname,
                                  node.host_ip, node.running_vms))
        return discovery


class Node(base.Resource):

    def __init__(self, uuid, name, host_ip, running_vms):
        super(Node, self).__init__(uuid, name)
        self.host_ip = host_ip
        self.running_vms = running_vms

    def __repr__(self):
        return ("<Node(uuid={0}, name={1}, host_ip={2})>"
                .format(self.uuid, self.name, self.host_ip))
