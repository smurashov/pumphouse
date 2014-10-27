import logging

from taskflow.patterns import graph_flow
from sets import Set

# from pumphouse import task

LOG = logging.getLogger(__name__)

# Useful documentation
# http://docs.openstack.org/user-guide/content/sdk_neutron_apis.html

# Port
# http://docs.openstack.org/api/openstack-network/2.0/content/Overview-d1e71.html


def get_port_by(client, **port_filter):
    try:
        LOG.debug("port_filter: %s" % str(port_filter))
        return client.list_ports(**port_filter)['ports'].to_dict()
    except Exception as e:
        LOG.exception("Error in listing ports: %s" % e.message)
        raise


def get_security_groups_by(client, **sg_filter):
    try:
        LOG.debug("security_groups_filter: %s" % str(sg_filter))
        return client.list_security_groups(**sg_filter)
    except Exception as e:
        LOG.exception("Error in security_groups: %s" % e.message)
        raise


def get_subnet_by(client, **subnet_filter):
    try:
        LOG.debug("subnet filter: %s" % str(subnet_filter))
        return client.list_subnets(**subnet_filter)
    except Exception as e:
        LOG.exception("Error in subnet: %s" % e.message)


# Network. An isolated virtual layer-2 domain. A network can also be a
# virtual, or logical, switch.
def get_network_by(client, **net_filter):
    try:
        LOG.debug("get_network_by: %s" % str(net_filter))
        return client.list_networks(**net_filter)['network'].to_dict()
    except Exception as e:
        LOG.exception("Error in network: %s" % e.message)


def del_port(client, **port_filter):
    try:
        i = 0
        for port in get_port_by(client, **port_filter):
            client.delete_port(id=port['id'])
            i = i + 1
        return i
    except Exception as e:
        LOG.exception("Error in delete port: %s, pord_id: %s" %
                      (e.message, str(port_filter)))
        raise


def create_port(client, **create_params):
    default_params = {
        "admin_state_up": True,  # Administrative state of port.
        """Indicates whether network is currently operational.
           Possible values include: ACTIVE, DOWN, BUILD, ERROR"""
        "status": "ACTIVE",
    }
    required_params = ["mac_address"]

    port_params = default_params.update(dict(create_params))

    for required in required_params:
        if required not in port_params or not port_params[required]:
            LOG.warning("Required property '%s' is not set" % required)
            return -1

    if (port_params['status'] != "ACTIVE"):
        LOG.warning('Create port with status != ACTIVE')

    try:
        LOG.debug("Create port %s" % str(port_params))
        return client.create_port(body=port_params)['port']
    except Exception as e:
        LOG.exception("Error in create_port: %s, params: %s" %
                      (e.message, str(port_params)))
        raise


def get_security_groups(client, **sg_filter):
    try:
        return get_security_groups(**sg_filter)['security_groups']
    except Exception as e:
        LOG.exception("Error in get security groups: %s, filer: %s" %
                      (e.message, str(sg_filter)))
        raise


def del_security_groups(client, **sg_filter):
    try:
        i = 0
        for security_group in get_security_groups_by(**sg_filter):
            client.delete_security_group(
                security_group_id=security_group['id'])
            i = i + 1
        return i
    except Exception as e:
        LOG.exception("Error in del security groups: %s, filter: %s" %
                      (e.message, str(sg_filter)))
        raise


# XXX Intersects with nova security groups
# implements?
def create_security_group(client, **sg_params):
    try:
        return client.create_sequrity_group(sg_params)
    except Exception as e:
        LOG.exception("Error in get security groups: %s" % e.message)
        raise


def list_subnets(client, net_id):
    try:
        return get_subnet_by(client, network_id=net_id)['subnets']
    except Exception as e:
        LOG.exception("Error in list subnets: %s" % e.message)
        raise


def del_subnet(client, **subnet_filter):
    try:
        i = 0
        for subnet in get_subnet_by(client, subnet_filter):
            LOG.debug("Delete subnet '%s' match by '%s' filter" %
                      (subnet['id'], str(subnet_filter)))
            client.delete_subnet(subnet_id=subnet['id'])
            i = i + 1
        return i
    except Exception as e:
        LOG.exception(
            "Error in list subnets: %s" % e.message)
    raise


def create_subnet(client, **subnet_params):
    # FIXME (verify args)
    try:
        LOG.debug("Create subnet '%s'" % (str(subnet_params)))
        return client.create_subnet(**subnet_params)
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


def migrate_neutron_ports(context, server_id):
    network_dep = Set()
    subnet_dep = Set()

    ports = get_port_by(context.src_cloud, device_id=server_id):

    for port in ports:
        try:
            network_dep.add(port['network_id'])
            subnet_dep.update(set(ip['subnet_id'] for ip in port['fixed_ips']))
        except KeyError:
            LOG.exception("Missing keys in get_port_by asnwer: %s" % str(port))
            raise

def RetrieveNeutronNetwork(task.BaseCloudTask):
    def execute(self, net_id):
        try:
            return get_network_by(self.cloud.neutron, id = net_id)[0]
        except IndexError:
            LOG.exception("Empty answer for network_id: %s" % str(network_id))
            raise


def RetrieveNeutronPort(task.BaseCloudTask):
    def execute(self, port_id):
        try:
            return get_port_by(self.cloud.neutron, id=port_id)[0]
        except IndexError:
            LOG.exception("Empty answer for port_id: %s" % str(port_id))
            raise

def EnsureNeutronPort(task.BaseCloudTask):
    def verifyPort(self, dstPort, srtPort):
        # TODO (sryabin) more complex check
        try:
            return dstPort['mac_address'] == srtPort['mac_address']
        except KeyError:
            LOG.exception("Wrong dicts for port verifying: %s" % str(port_id))
            raise
    def execute(self, port_id, port_data):
        try:
            port = get_port_by(self.cloud.neutron, id=port_id)[0]
        except IndexError:
            # port not found
            # XXX (sryabin) stub
            return create_port(self.cloud.neutron, port_data)
        else:
            sert self.verifyPort(port, port_data) == 1




def migrate_ports(context, port_id):
    port_binding = "neutron-network-port-{}".format(port_id)
    port_retrieve = "{}-retrieve".format(port_binding)
    port_ensure = "{}-ensure".format(port_binding)

    if (port_binding in context.store):
        return None, port_ensure

#   flow.add()


def migrate_network(context, tenant_id, network_id=None):
    # all_networks = get_network_by()
    # XXX (sryabin) nova migration driver uses "networks-src, networks-dst"
    all_src_networks = "neutron-network-src"
    all_dst_networks = "neutron-network-dst"

    network_binding = "neutron-network-{}".format(
        network_id)
    network_retrieve = "{}-retrieve".format(
        network_binding)
    network_ensure = "{}-ensure".format(network_binding)

    if (network_binding in context.store):
        return None, network_ensure

    flow = graph_flow.Flow(
        "migrate-{}".format(network_binding))

    if ("all_src_networks_retrieve" not in context.store):
        context.store[all_src_networks] = None

#        flow.add(RetrieveAllNetworks(context.src_cloud,
#                                     name=all_src_networks,
#                                     provides=all_src_networks))
#

    if ("all_dst_networks_retrieve" not in context.store):
        context.store[all_dst_networks] = None

#        flow.add(RetrieveAllNetworks(context.dst_cloud,
#                                     name=all_dst_networks,
#                                     provides=all_dst_networks))


#    flow.add(EnsureNetwork(context.dst_cloud,
#                           name=network_ensure,
#                           rebind=[all_dst_networks, network_retrieve]))

    return flow, network_ensure
