import logging

from taskflow.patterns import graph_flow

from pumphouse import task

LOG = logging.getLogger(__name__)

# Port http://docs.openstack.org/api/openstack-network/2.0/content/Overview-d1e71.html
def get_port_by(client, **port_filter): 
    try:
        LOG.debug("port_filter: %s", str(port_filter)) 
        return client.list_ports( **port_filter )['ports'] 
    except Exception as e:
        LOG.exception("Error in listing ports: %s" % e.message)
        raise

def get_security_groups_by(client, **sg_filter): 
    try:
        LOG.debug("security_groups_filter: %s", str(sg_filter)) 
        return client.list_security_groups( **sg_filter )
    except Exception as e:
        LOG.exception("Error in security_groups: %s" % e.message)
        raise

def get_subnet_by(client, **subnet_filter): 
    try:
        LOG.debug("subnet filter: %s", str(subnet_filter)) 
        return client.list_subnets( **subnet_filter )
    except Exception as e:
        LOG.exception("Error in subnet: %s" % e.message)
        

# Network. An isolated virtual layer-2 domain. A network can also be a virtual, or logical, switch.
def get_network_by(client, **net_filter):
    try:
        LOG.debug("get_network_by: %s", str(net_filter)) 
        return client.list_networks( **net_filter )
    except Exception as e:
        LOG.exception("Error in network: %s" % e.message)
    

def del_port(client, **port_filter):
    try:
        i = 0 
        for port in get_port_by(client, **port_filter):
            client.delete_port( id = port['id']
            i++
        return i
    except Exception as e:
        LOG.exception("Error in delete port: %s, pord_id: %s" %
                      (e.message, port_id))
        raise


def create_port(client, **create_params):
    default_params = {
        "admin_state_up": True,  # Administrative state of port.
    } 
    required_params = [ "network_id", "subnet_id", "tenant_id" ]


    port_params = default_params.update(dict(create_params)) 

    for required in required_params:
        if required not in port_params or not port_params[required]:
            LOG.warning("Require network_id and subnet_id properties")
            return -1

    try:
        return client.create_port(body = port_params)['port']
    except Exception as e:
        LOG.exception("Error in create_port: %s, network_id: %s, mac: %s, \
            ip_address: %s" % (e.message, network_id, mac, ip_address))
        raise


def get_security_groups(client, **sg_filter):
    try:
        return get_security_groups( **sg_filter )['security_groups']
    except Exception as e:
        LOG.exception("Error in get security groups: %s" % e.message)
        raise


def del_security_groups(client, **sg_filter ):
    try:
        i = 0
        for security_group in get_security_groups_by( **sg_filter):
            client.delete_security_group(security_group_id = security_group['id'])
            i++
        return i
    except Exception as e:
        LOG.exception("Error in get security groups: %s" % e.message)
        raise


def create_security_group(client, name, description):
    try:
        return client.create_sequrity_group({
            "security_group": {
                "name": name,
                "description": description,
            },
        })
    except Exception as e:
        LOG.exception("Error in get security groups: %s" % e.message)
        raise

def list_subnets(client, net_id):
    try:
        return get_subnet_by(client, network_id = net_id)['subnets']
    except Exception as e:
        LOG.exception("Error in list subnets: %s" % e.message)
        raise


def del_subnet(client, **subnet_filter):
    try:
        i = 0
        for subnet in get_subnet_by(client, subnet_filter): 
            client.delete_subnet( subnet_id = subnet['id'] )
            i++
        return i
    except Exception as e:
        LOG.exception("Error in list subnets: %s" % e.message)
        raise


def create_subnet(client, network_id, cidr, tenant_id):
    # FIXME (verify args)
    try:
        return client.create_subnet({
            "subnet": {
                "networki_id": tenant_id,
                "ip_version": 4,
                "cidr": cidr,
                "tenant_id": tenant_id
            },
        })
    except Exception as e:
        LOG.exception("Error in list subnets: %s" % e.message)
        raise


def create_network(client, network_name):
    try:
        return client.create_network({
                                     'network': network_name
                                     })
    except Exception as e:
        LOG.exception("Error in list subnets: %s" % e.message)
        raise


def list_network(client, net_info, tenant_id):
    try:
        if net_info:
            if 'id' in net_info:
                return client.list_networks(network_id=net_info['id'])['networks'][0]
            elif 'name' in net_info:
                return \
                    client.list_networks(name=net_info['name'])['networks'][0]
        else:
            return client.list_networks()
    except Exception as e:
        LOG.exception("Error in get network: %s" % e.message)
        raise


class RetrieveAllNetworks(task.BaseCloudTask):

    def execute(self):
        return list_network(self.cloud.neutron, None)


class RetrieveAllNetworksById(task.BaseCloudTask):

    def execute(self, network_id):
        return list_network(self.cloud.neutron, {"name": network_id})


class EnsureNetwork(task.baseCloudTask):

    def exists(self, network_id):
        return 1 if list_network(self.cloud.neutron, {"id": network_id}) \
            else 0

    def exceute(self, network_id):
        if not self.exists(network_id):
            create_network(self.cloud.neutron, network_id)
        return list_network(self.cloud.neutron, {"id": network_id})


class RetrievePorts(task.baseCloudTask):
    def execute(self, net_id):
        return get_port_by(self.cloud.neutron, network_id = net_id)



def migrate_ports(context, port_id):
    port_binding = "neutron-network-port-{}".format(port_id)
    port_retrieve = "{}-retrieve".format(port_biding)
    port_ensure = "{}-ensure".format(port_biding)

    if (port_binding in context.store):
        return None, port_ensure

    flow = graph_flow.Flow("migrate-{}".format(port_binding))
#   flow.add()

# In the Networking API v2.0, the network is the main entity. 
# Ports and subnets are always associated with a network.
def migrate_network(context, network_id=None, tenant_id):
    all_networks = list_network(context.dst_cloud, network_id, tenant_id)
    # XXX (sryabin) nova migration driver uses "networks-src, networks-dst"
    # consts
    all_src_networks = "neutron-network-src"
    all_dst_networks = "neutron-network-dst"

    network_binding = "neutron-network-{}".format(network_id)
    network_retrieve = "{}-retrieve".format(network_binding)
    network_ensure = "{}-ensure".format(network_binding)

    if (network_binding in context.store):
        return None, network_ensure

    flow = graph_flow.Flow("migrate-{}".format(network_binding))

    if ("all_src_networks_retrieve" not in context.store):
        flow.add(RetrieveAllNetworks(context.src_cloud,
                                     name=all_src_networks,
                                     provides=all_src_networks))
        context.store[all_src_networks] = None

    if ("all_dst_networks_retrieve" not in context.store):
        flow.add(RetrieveAllNetworks(context.dst_cloud,
                                     name=all_dst_networks,
                                     provides=all_dst_networks))
        context.store[all_dst_networks] = None

    flow.add(EnsureNetwork(context.dst_cloud,
                           name=network_ensure,
                           rebind=[all_dst_networks, network_retrieve]))

    return flow, network_ensure
