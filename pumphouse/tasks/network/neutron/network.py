import logging

from taskflow.patterns import graph_flow
from sets import Set

from pumphouse import exceptions
from pumphouse import task


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

def del_network(client, network_filter):
    try:
        for network in get_networks_by(network_filter):
            LOG.debug("Delete network '%s' match by '%s' filter" %
                      (network['id'], str(subnet_filter)))
            client.delete_network(network['id'])
    except Exception as e:
        LOG.exception("Error in delete network: %s" % e.message)
        raise



def create_network(client, network_data):
    try:
        # TODO (sryabin) stub create_network
        return client.create_network({
            'network': network_data
        })
    except Exception as e:
        LOG.exception("Error in list subnets: %s" % e.message)
        raise


class RetrieveNeutronNetwork(task.BaseCloudTask):

    def execute(self, net_id):
        try:
            return get_network_by(self.cloud.neutron, id=net_id)[0]
        except IndexError:
            raise exceptions.Error(
                "Empty answer for network_id: %s" % str(net_id))


class RetrieveNeutronPort(task.BaseCloudTask):

    def execute(self, port_id):
        try:
            return get_port_by(self.cloud.neutron, id=port_id)[0]
        except IndexError:
            raise exceptions.Error(
                "Empty answer for port_id: %s" % str(port_id))


class RetrieveNeutronSubnet(task.BaseCloudTask):

    def execute(self, subnet_id):
        try:
            return get_subnet_by(self.cloud.neutron, id=subnet_id)[0]
        except IndexError:
            LOG.exception("Empty answer for subnet_id: %s" % str(subnet_id))
            raise


class EnsureNeutronPort(task.BaseCloudTask):

    def verifyPort(self, src_port, dst_port):
        # TODO (sryabin) more complex check
        try:
            return dst_port['mac_address'] == src_port['mac_address']
        except KeyError:
            raise exceptions.Error("Bad dicts src: %s, dst: %s" %
                                   (str(src_port), str(dst_port)))

    def execute(self, port_id, port_data):
        try:
            port = get_port_by(self.cloud.neutron, id=port_id)[0]
        except IndexError:
            # port not found
            # XXX (sryabin) stub
            return create_port(self.cloud.neutron, port_data)
        else:
            assert self.verifyPort(port, port_data) == 1
            return port


class EnsureNeutronSubnet(task.BaseCloudTask):

    # XXX (sryabin) similar verify in EnsureNeutronNetwork
    def verifySubnet(self, src_subnet, dst_subnet):
        try:
            # TODO (sryabin) more complex check
            return src_subnet['name'] == dst_subnet['name']
        except KeyError:
            raise exceptions.Error("Bad dicts src: %s, dst: %s" %
                                   (str(src_subnet), str(dst_subnet)))

    def execute(self, subnet):
        try:
            dst_subnet = get_port_by(
                self.cloud.neutron, name=subnet['name'])[0]
        except IndexError:
            # subnet not found in dst cloud
            # TODO (sryabin) stub
            # TODO (sryabin) catch KeyError
            return create_subnet(self.cloud.neutron, subnet)
        else:
            assert self.verifySubnet(subnet, dst_subnet)
            return subnet


class EnsureNeutronNetwork(task.BaseCloudTask):
    # XXX (sryabin) similar verify in EnsureNeutronSubnet

    def verify(self, src, dst):
        try:
            return src['name'] == dst['name']
        except KeyError:
            raise exceptions.Error("Bad dicts src: %s, dst: %s" %
                                   (str(src), str(dst)))

    def execute(self, src):
        try:
            # TODO (sryabin) catch KeyError
            # TODO (sryabin) stub
            dst = get_network_by(self.cloud.neutron, name=src['name'])
        except IndexError:
            return create_network(self.cloud.neutron, src)
        else:
            assert self.verify(src, dst)
            return dst


def migrate_neutron_network(context, network_id):
    network_binding = "neutron-network-{}".format(network_id)

    if (network_binding in context.store):
        return None

    # generate new flor for network migration
    flow = graph_flow.Flow("migrate-neutron-network-{}".format(network_id))

    network_retrieve = "{}-retrieve".format(network_binding)
    network_ensure = "{}-ensure".format(network_binding)

    flow.add(RetrieveNeutronNetwork(context.src_cloud,
                                    name=network_binding,
                                    provides=network_binding))

    flow.add(EnsureNeutronNetwork(context.dst_cloud,
                                  name=network_ensure,
                                  provides=network_ensure))

    context.store[network_binding] = None

    return flow


def migrate_neutron_subnet(context, subnet_id):
    subnet_binding = "neutron-network-subnet-{}".format(subnet_id)

    if (subnet_binding in context.store):
        return None

    flow = graph_flow.Flow(
        "migrate-neutron-network-subnet-{}".format(subnet_id))

    # generate new flow for subnet migration
    subnet_retrieve = "{}-retrieve".format(subnet_binding)
    subnet_ensure = "{}-ensure".format(subnet_binding)

    flow.add(RetrieveNeutronSubnet(context.src_cloud,
                                   name=subnet_binding,
                                   provides=subnet_binding))
    flow.add(EnsureNeutronSubnet(context.dst_cloud,
                                 name=subnet_ensure,
                                 provides=subnet_ensure))

    context.store[subnet_binding] = None

    return flow


def migrate_single_neutron_port(context, port):
    port_binding = "neutron-net-port-{}".format(port['id'])
    port_retrieve = "{}-retrieve".format(port_binding)
    port_ensure = "{}-ensure".format(port_binding)

    flow = graph_flow.Flow(
        "migrate-neutron-network-port-{}".format(port['id']))

    if (port_binding in context.store):
        return None, port_ensure

    try:
        subnet_flow = migrate_neutron_subnet(context, port['subnet_id'])
        if (subnet_flow):
            flow.add(subnet_flow)
    except KeyError:
        pass

    try:
        network_flow = migrate_neutron_network(context, port['network_id'])
        if (network_flow):
            flow.add(network_flow)
    except KeyError:
        pass

    flow.add(RetrieveNeutronPort(context.src._cloud,
                                 name=port_binding,
                                 provides=port_binding))
    flow.add(EnsureNeutronPort(context.dst_cloud,
                               name=port_ensure,
                               provides=port_ensure))

    context.store[port_binding] = None

    return flow


def migrate_neutron_ports(context, server_id):
    network_dep = Set()
    subnet_dep = Set()

    ports = get_port_by(context.src_cloud, device_id=server_id)

    if (not len(ports)):
        LOG.warning("server_id: %d no port assignmnet" % server_id)
        return None, None

    flow = graph_flow.Flow("migrate-neutron-network-{}".format(server_id))

    for port in ports:
        try:
            # TODO (sryabin) change namespace policy to
            # neutron-net-(network|subnet|port)-{}.format(entity_id)
            port_flow = migrate_single_neutron_port(context, port)
            if (port_flow):
                flow.add(port_flow)

        except KeyError:
            raise exceptions.Error(
                "Missing keys in get_port_by asnwer: %s" % str(port))

    return flow


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
