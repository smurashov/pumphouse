from neutronclient.neutron import client
import pprint
import inspect

from taskflow import engines
from taskflow import task
from taskflow.patterns import linear_flow
from taskflow.patterns import graph_flow
from collections import defaultdict

import novaclient.client
import re


def get_port_by(neutron, port_filter):
    try:
        return neutron.list_ports(**port_filter)['ports']
    except Exception as e:
        raise

def get_subnet_by(neutron, subnet_filter):
    try:
        return neutron.list_subnets(**subnet_filter)['subnets']
    except Exception as e:
        raise e


def get_router_by(neutron, router_filter):
    try:
        return neutron.list_routers(**router_filter)['routers']
    except Exception as e:
        raise e

def get_router_by(neutron, router_filter):
    try:
        return neutron.list_routers(**router_filter)['routers']
    except Exception as e:
        raise e

def get_floatingIp_by(neutron, floatingIp_filter):
    try:
        return neutron.list_floatingips(**floatingIp_filter)["floatingips"]
    except Exception as e:
        raise e

def get_securityGroups_by(neutron, security_groups_filter):
    try:
        return neutron.list_security_groups(**security_groups_filter)['security_groups']
    except Exception as e:
        raise e

def create_securityGroup_rule(neutron, security_group_rule_info):
    try:
        return neutron.create_security_group_rule( { 'security_group_rule' : security_group_rule_info } )
    except Exception as e:
        raise e



def create_network(neutron, net_info):
    try:
        return neutron.create_network({'network': net_info })['network']
    except Exception as e:
        raise e

def create_subnet(neutron, subnet_info):
    try:
        return neutron.create_subnet({'subnet': subnet_info})['subnet']
    except Exception as e:
        raise e

def create_port(neutron, port_info):
    try:
        return neutron.create_port(body = { 'port': port_info })['port']
    except Exception as e:
        raise e

def create_security_group(neutron, security_group_info):
    try:
        return neutron.create_security_group( {'security_group': security_group_info })['security_group']
    except Exception as e:
        raise e

class BaseCloudTask(task.Task):
    neutron = None
    def __init__(self, ip, *args, **kwargs):
        super(BaseCloudTask, self).__init__(*args, **kwargs)
        URL = "http://" + ip + ":5000/v2.0"
        self.cloud.neutron = client.Client('2.0', username='admin', password='admin', tenant_name='admin', auth_url=URL)
        self.nova = novaclient.client.Client('2', 'admin', 'admin', 'admin', auth_url=URL)
        self.log("init")


    def log(self, message):
        print("%s: %s" % (self.__class__.__name__, message))

class BaseCloud():
    def __init__(self, ip):
        URL = "http://" + ip + ":5000/v2.0"
        self.cloud.neutron = client.Client('2.0', username='admin', password='admin', tenant_name='admin', auth_url=URL)
        self.nova = novaclient.client.Client('2', 'admin', 'admin', 'admin', auth_url=URL)

class RetrieveNeutronNetworks(BaseCloudTask):
    def execute(self):
        return self.cloud.neutron.list_networks()['networks']

class RetrieveNetworkById(BaseCloudTask):
    def execute(self, sourceNeutronNetworks, net_id):
        for net in sourceNeutronNetworks:
            if (net['id'] == net_id):
                self.log("Match network %s" % net_id)
                return net

class RetrieveAllPorts(BaseCloudTask):
    def execute(self):
        return self.cloud.neutron.list_ports()['ports']

class RetrieveAllSubnets(BaseCloudTask):
    def execute(self):
        return get_subnet_by(self.cloud.neutron, {})

class RetrieveAllRouters(BaseCloudTask):
    def execute(self):
        return get_router_by(self.cloud.neutron, {})

class RetrieveSubnetById(BaseCloudTask):
    def execute(self, subnets, subnet_id):
        for subnet in subnets:
            if (subnet['id'] == subnet_id):
                return subnet

        return None

class RetrieveRouterById(BaseCloudTask):
    def execute(self, all_routers, router_id):
        for router in all_routers:
            if (router['id'] == router_id):
                return router

        return None

class EnsureRouter(BaseCloudTask):
    def execute(self, all_routers, router_info):
        for router in all_routers:
            if (router["name"] == router_info["name"]):
                return router

        del router_info['id']

        router = self.cloud.neutron.create_router(
            { 'router': router_info }
        )['router']
        return router


class EnsureSubnet(BaseCloudTask):
    def execute(self, subnets, subnet_info, network_info):
        for subnet in subnets:
            if (subnet['name'] == subnet_info['name']):
                self.log("Subnet %s is allready exists, name: %s" % (subnet_info['id'], subnet_info['name']))
                return subnet

        self.log("Subnet not found, name: %s" % subnet_info['name'])

        subnet = create_subnet(self.cloud.neutron, {
            'allocation_pools': subnet_info['allocation_pools'],
            'cidr': subnet_info['cidr'],
            'ip_version': subnet_info['ip_version'],
            'gateway_ip': subnet_info['gateway_ip'],
            'name': subnet_info['name'],
            'network_id': network_info['id']
        })

        self.log("Subnet %s created: %s" % (subnet['id'], str(subnet)))

        return subnet


class EnsureNetwork(BaseCloudTask):
    def execute(self, networks, net_info):
        for net in networks:
            if (net['name'] == net_info['name']):
                self.log("Network %s is allready exists, name: %s" % (net_info['id'], net['name']))
                return net

        self.log("Network %s not exists" % net_info['id'])

        network = create_network(self.cloud.neutron, {
            'name': net_info['name']
        })

        self.log("Network %s created: %s" % network['id'], str(network))

        return network

class RetrievePortById(BaseCloudTask):
    def execute(self, all_ports, port_id):
        for port in all_ports:
            if port["id"] == port_id:
                self.log("port found %s " % str(port))
                return port

        return None

class EnsurePort(BaseCloudTask):
    def execute(self, all_ports, port_info, network_info, subnet_info, device_info):
        for port in all_ports:
            if (port['mac_address'] == port_info['mac_address']):
                return port


        SKIP_PROPS = [ 'device_id', 'id', 'security_groups', 'fixed_ips', 'status', 'binding:vif_details', 'binding:vif_type' ]

        for prop in SKIP_PROPS:
            if prop in port_info:
                self.log("removed prop: %s" % prop);
                del port_info[prop]

        port_info['network_id'] = network_info['id']

        port = create_port(self.cloud.neutron, port_info)

        return port

class RetrieveFloatingIps(BaseCloudTask):
    def execute(self):
        return get_floatingIp_by(self.cloud.neutron, {})

class RetrieveFloatingIpById(BaseCloudTask):
    def execute(self, all_floatingips, floating_id):
        for floating_ip in all_floatingips:
            if (floating_ip['id'] == floating_id):
                return floating_ip

        return None

class EnsureFloatingIp(BaseCloudTask):
    def execute(self, all_floatingips, floating_info):
        # TODO add server_id to arguments
        for floating_ip in all_floatingips:
            if (floating_ip['floating_ip_address'] == floating_info['floating_ip_address']):
                return floating_ip

        del floating_info['id']

        floating_ip = self.cloud.neutron.create_floatingip(
            { 'floatingip': floating_info }
        )

        return floating_ip



class RetrieveSecurityGroups(BaseCloudTask):
    def execute(self):
        return get_securityGroups_by(self.cloud.neutron, {})

class RetrieveSecurityGroupById(BaseCloudTask):
    def execute(self, all_security_groups, security_id):
        for security_group in all_security_groups:
            if (security_group['id'] == security_id):
                return security_group

        return None

class EnsureSecurityGroup(BaseCloudTask):
    def execute(self, all_security_groups, security_group_info, port_info):

        for security_group in all_security_groups:
            if (security_group['name'] == security_group_info['name']):
                # XXX check security group assigned to port
                self.log("security '%s' group already exists %s" % (security_group['name'], str(security_group)))
                return security_group


        self.log("security '%s' group not exists" % security_group_info['name'])

        security_group_rules = security_group_info['security_group_rules']

        del security_group_info['id'], security_group_info['security_group_rules']
        security_group = create_security_group(self.cloud.neutron, security_group_info)

        for rule in security_group_rules:
            del rule['id'], rule['tenant_id']
            rule['security_group_id'] = security_group['id']
            create_securityGroup_rule(self.cloud.neutron, rule)

        if security_group['id'] not in port_info['security_groups']:
            port_info['security_groups'].append(security_group['id'])
            self.cloud.neutron.update_port(port_info['id'], {
                'port': { 'security_groups': port_info['security_groups'] }
            })


        return security_group


def migrate_floatingip(context, floatingip_id):

    floatingip_binding = floatingip_id

    floatingip_retrieve = "migrate-neutron-floatingip-{}-retrieve".format(floatingip_binding)
    floatingip_ensure = "migrate-neutron-floatingip-{}-ensure".format(floatingip_binding)

    (retrieve, ensure) =  generate_binding(floatingip_binding, inspect.stack()[0][3])
    #(router_retrieve, router_ensure) = generate_binding(router_binding, inspect.stack()[0][3])

    if (floatingip_binding in context):
        return None, floatingip_retrieve

    context[floatingip_binding] = floatingip_id

    f = graph_flow.Flow("neutron-floatingip-migration-{}".format(floatingip_binding))

    all_src_floatingips_binding = "srcNeutronAllFloatingIps"
    all_dst_floatingips_binding = "dstNeutronAllFloatingIps"

    if (all_src_floatingips_binding not in context):
        f.add(RetrieveFloatingIps(
            context.src_cloud,
            name = "retrieveAllSrcFloatingIps",
            provides = all_src_floatingips_binding
        ))
        context[all_src_floatingips_binding] = None

    if (all_dst_floatingips_binding not in context):
        f.add(RetrieveFloatingIps(
            "172.16.0.16",
            name = "retrieveDstAllFloatingIps",
            provides = all_dst_floatingips_binding
        ))
        context[all_dst_floatingips_binding] = None



    f.add(RetrieveFloatingIpById(context.src_cloud,
        name = floatingip_retrieve,
        provides = floatingip_retrieve,
        rebind = [ all_src_floatingips_binding, floatingip_binding ],
    ))

    f.add(EnsureFloatingIp("172.16.0.16",
        name = floatingip_ensure,
        provides = floatingip_ensure,
        rebind = [ all_dst_floatingips_binding, floatingip_retrieve ]
    ))

    return f, floatingip_ensure



def migrate_network(context, network_id):

    network_binding = network_id

    network_retrieve = "migrate-neutron-network-{}-retrieve".format(network_binding)
    network_ensure = "migrate-neutron-network-{}-ensure".format(network_binding)

    if (network_binding in context):
        return None, network_retrieve

    context[network_binding] = network_id

    f = graph_flow.Flow("neutron-network-migration-{}".format(network_binding))

    all_src_networks_binding = "srcNeutronAllNetworks"
    all_dst_networks_binding = "dstNeutronAllNetworks"

    if (all_src_networks_binding not in context):
        f.add(RetrieveNeutronNetworks(
            context.src_cloud,
            name = "retrieveAllSrcNetworks",
            provides = all_src_networks_binding
        ))
        context[all_src_networks_binding] = None

    if (all_dst_networks_binding not in context):
        f.add(RetrieveNeutronNetworks(
            "172.16.0.16",
            name = "retrieveDstAllNetworks",
            provides = all_dst_networks_binding
        ))
        context[all_dst_networks_binding] = None



    f.add(RetrieveNetworkById(context.src_cloud,
        name = network_retrieve,
        provides = network_retrieve,
        rebind = [ all_src_networks_binding, network_binding ],
    ))

    f.add(EnsureNetwork("172.16.0.16",
        name = network_ensure,
        provides = network_ensure,
        rebind = [ all_dst_networks_binding, network_retrieve ]
    ))

    return f, network_ensure

def migrate_securityGroup(context, securityGroup_id, port_binding):
    securityGroup_binding = securityGroup_id

    securityGroup_retrieve = "migrate-neutron-securityGroup-{}-retrieve".format(securityGroup_binding)
    securityGroup_ensure = "migrate-neutron-securityGroup-{}-ensure".format(securityGroup_binding)

    if (securityGroup_binding in context):
        return None, securityGroup_ensure

    context[securityGroup_binding] = securityGroup_id

    f = graph_flow.Flow("neutron-securityGroup-migration-{}".format(securityGroup_id))

    all_src_securityGroup_binding = "srcNeutronAllSecurityGroups"
    all_dst_securityGroup_binding = "dstNeutronAllSecurityGroups"

    if (all_src_securityGroup_binding not in context):

        f.add(RetrieveSecurityGroups(
            context.src_cloud,
            name = "retrieveAllSrcSecurityGroups",
            provides = all_src_securityGroup_binding
        ))


        context[all_src_securityGroup_binding] = None

    if (all_dst_securityGroup_binding not in context):

        f.add(RetrieveSecurityGroups(
            "172.16.0.16",
            name = "retrieveAllDstSecurityGroups",
            provides = all_dst_securityGroup_binding
        ))

        context[all_dst_securityGroup_binding] = None

    f.add(RetrieveSecurityGroupById(context.src_cloud,
        name = securityGroup_retrieve,
        provides = securityGroup_retrieve,
        rebind = [ all_src_securityGroup_binding, securityGroup_binding ]
    ))

    f.add(EnsureSecurityGroup("172.16.0.16",
        name = securityGroup_ensure,
        provides = securityGroup_ensure,
        rebind = [ all_dst_securityGroup_binding, securityGroup_retrieve, port_binding ]
    ))

    return f, securityGroup_ensure



def migrate_subnet(context, subnet_id, network_info):

    subnet_binding = subnet_id

    subnet_retrieve = "migrate-neutron-subnet-{}-retrieve".format(subnet_binding)
    subnet_ensure = "migrate-neutron-subnet-{}-ensure".format(subnet_binding)

    if (subnet_binding in context):
        return None, subnet_ensure

    context[subnet_binding] = subnet_id

    f = graph_flow.Flow("neutron-subnet-migration-{}".format(subnet_id))

    all_src_subnet_binding = "srcNeutronAllSubnets"
    all_dst_subnet_binding = "dstNeutronAllSubnets"

    if (all_src_subnet_binding not in context):

        f.add(RetrieveAllSubnets(
            context.src_cloud,
            name = "retrieveAllSrcSubnets",
            provides = all_src_subnet_binding
        ))


        context[all_src_subnet_binding] = None

    if (all_dst_subnet_binding not in context):

        f.add(RetrieveAllSubnets(
            "172.16.0.16",
            name = "retrieveAllDstSubnets",
            provides = all_dst_subnet_binding
        ))

        context[all_dst_subnet_binding] = None

    f.add(RetrieveSubnetById(context.src_cloud,
        name = subnet_retrieve,
        provides = subnet_retrieve,
        rebind = [ all_src_subnet_binding, subnet_binding ]
    ))

    f.add(EnsureSubnet("172.16.0.16",
        name = subnet_ensure,
        provides = subnet_ensure,
        rebind = [ all_dst_subnet_binding, subnet_retrieve, network_info ]
    ))

    return f, subnet_ensure

def migrate_router(context, router_id):

    router_binding = router_id

    #router_retrieve = "migrate-neutron-router-{}-retrieve".format(router_binding)
    #router_ensure = "migrate-neutron-router-{}-ensure".format(router_binding)
    (router_retrieve, router_ensure) = generate_binding(router_binding, inspect.stack()[0][3])

    if (router_binding in context):
        return None, router_ensure

    context[router_binding] = router_id

    f = graph_flow.Flow("neutron-router-migration-{}".format(router_id))

    all_src_router_binding = "srcNeutronAllRouters"
    all_dst_router_binding = "dstNeutronAllRouters"

    if (all_src_router_binding not in context):

        f.add(RetrieveAllRouters(
            context.src_cloud,
            name = "retrieveAllSrcRouters",
            provides = all_src_router_binding
        ))


        context[all_src_router_binding] = None

    if (all_dst_router_binding not in context):

        f.add(RetrieveAllRouters(
            "172.16.0.16",
            name = "retrieveAllDstRouters",
            provides = all_dst_router_binding
        ))

        context[all_dst_router_binding] = None

    f.add(RetrieveRouterById(context.src_cloud,
        name = router_retrieve,
        provides = router_retrieve,
        rebind = [ all_src_router_binding, router_binding ]
    ))

    f.add(EnsureRouter("172.16.0.16",
        name = router_ensure,
        provides = router_ensure,
        rebind = [ all_dst_router_binding, router_retrieve ]
    ))

    return f, router_ensure


def migrate_port(context, port_id, destination_instance_id):



    port_binding = port_id

    if (port_binding in context):
        return None

    context[port_binding] = port_id

    f = graph_flow.Flow("neutron-port-migration-{}".format(port_binding))

    port_info = get_port_by(context.src_cloud, { 'id': port_id })[0]

    all_src_ports_binding = "srcNeutronAllPorts"
    all_dst_ports_binding = "dstNeutronAllPorts"

    if (all_src_ports_binding not in context):
        f.add(RetrieveAllPorts(
            context.src_cloud,
            name = "retrieveNeutronAllSrcPorts",
            provides = all_src_ports_binding
        ))
        context[all_src_ports_binding] = None

    if (all_dst_ports_binding not in context):
        f.add(RetrieveAllPorts(
            "172.16.0.16",
            name = "retrieveNeutronAllDstPorts",
            provides = all_dst_ports_binding
        ))
        context[all_dst_ports_binding] = None


    port_retrieve = "neutron-port-migration-{}-retrieve".format(port_binding)
    port_ensure = "neutron-port-migration-{}-ensure".format(port_binding)
    network_info = "NullNetworkInfo"
    subnet_info = "NullSubnet"
    device_info = "NullDevice"



    if ('network_id' in port_info and port_info['network_id'] is not None):
        networkFlow, network_info = migrate_network(context, port_info['network_id'])
        if (networkFlow is not None):
            f.add(networkFlow)

    # migrate subnet
    if ('fixed_ips' in port_info and port_info['fixed_ips'] is not None):
        for fixed_ip in port_info['fixed_ips']:
            if 'subnet_id' in fixed_ip:
                subnetFlow, subnet_info = migrate_subnet(context, fixed_ip['subnet_id'], network_info)
                if (subnetFlow is not None):
                    f.add(subnetFlow)

    if ("device_owner" in port_info):
        if (port_info['device_owner'] == 'network:floatingip'):
            floatingIpFlow, device_info = migrate_floatingip(context, port_info['device_id'])
            if (floatingIpFlow is not None):
                f.add(floatingIpFlow)
        elif (port_info["device_owner"] == "network:dhcp"):
            # migrate network
            return None
            #a = 2
        elif (port_info["device_owner"] == "network:router_gateway"):
            return None
            #a = 3
        elif (port_info['device_owner'] == 'compute:None'):
            a = 4
        elif (port_info["device_owner"] == "network:router_interface"):
            routerFlow, device_info = migrate_router(context, port_info['device_id'])
            if (routerFlow is not None):
                f.add(routerFlow)

        else:
            raise NotImplementedError("port %s have unknown device_owner %s" % (port_info["id"], port_info["device_owner"]))


    f.add(RetrievePortById(
        context.src_cloud,
        name = port_retrieve,
        provides = port_retrieve,
        rebind = [ all_src_ports_binding, port_binding ]
    ))

    context[device_info] = None

    f.add(EnsurePort(
        "172.16.0.16",
        name = port_ensure,
        provides = port_ensure,
        #rebind = [ all_dst_ports_binding, port_retrieve ]
        rebind = [ all_dst_ports_binding, port_retrieve, network_info, subnet_info, device_info ]
    ))

    if "security_groups" in port_info:
        for security_id in port_info["security_groups"]:
            securityGroupFlow, securityGroup_retrieve = migrate_securityGroup(context, security_id, port_ensure)
            if (securityGroupFlow is not None):
                f.add(securityGroupFlow)



    return f


PREFIX="neutron-"

def generate_binding(uid, label):
    label.replace("_","-")
    return PREFIX + "{}-{}-ensure".format(label, uid), PREFIX + "{}-{}-retrieve".format(label, uid)



def migrate_server(context, server_id, dst_server_id):


    f = graph_flow.Flow("neutron-server-migration-{}".format(server_id))

    for port in get_port_by(context.src_cloud, {'device_id': server_id}):
        f.add(migrate_port(context, port['id'], dst_server_id))

    return f




