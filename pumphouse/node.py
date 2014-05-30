import pump

class NodeDiscovery(pump.Discovery):

    def __init__(self):
        super(NodeDiscovery, self).__init__()
        service_type = 'compute'
        self.nova = client.Client(self.username,
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
    

class Node(pump.Resource):

    def __init__(self, uuid, name, host_ip, running_vms):
        super(Node, self).__init__(uuid, name)
        self.host_ip = host_ip
        self.running_vms = running_vms
