import logging

from taskflow.patterns import linear_flow

from pumphouse import task
from pumphouse import events
from pumphouse import exceptions
from pumphouse.tasks import utils as task_utils

# TODO (sryabin) create|del|list_security_group_rule implementation

def RetrieveAllNetworks(task.BaseCloudTask):
  def execute(self):
    return list_networks(self.cloud.neutron, None)

def RetrieveAllNetworksById(task.BaseCloudTask):
  def execute(self, network_id):
    return list_networks(self.cloud.neutron, { "name": network_id } )

def EnsureNetwork(task.baseCloudTask):
  def exists(self, network_id)
    return list_networks(self.cloud.neutron, { "id": network_id } ) ? 1 : 0
  def exceute(self, network_id) 
    if (!self.exists(network_id)): 
      create_network(self.cloud.neutron, network_id)
    return list_networks(self.cloud.neutron, { "id": network_id } )

def RetrievePorts(task.baseCloudTask):
  def execute(self)
    return list_ports(sefl.cloud.neutron);

def migrate_network(context, network_id = None):
  all_networks = list_networks(context.dst_cloud) 
  # XXX (sryabin) nova migration driver uses "networks-src, networks-dst" consts
  all_src_networks = "neutron-network-src"
  all_dst_networks = "neutron-network-dst"

  network_binding = "neutron-network-{}".format(network_id)
  network_retrieve = "{}-retrieve".format(network_binding)
  network_ensure = "{}-ensure".format(network_binding)
  
  if (network_binding in context.store):
    return None, network_ensure

  flow = graph_flow.Flow("migrate-{}".format(network_binding))

  if (all_src_networks_retrieve not in context.store):
    flow.add(RetrieveAllNetworks(context.src_cloud,
                                 name=all_src_networks
                                 provides=all_src_networks))
    context.store[all_src_networks] = None

  if (all_dst_networks_retrieve not in context.store):
    flow.add(RetrieveAllNetworks(context.dst_cloud,
                                 name=all_dst_networks
                                 provides=all_dst_networks))
    context.store[all_dst_networks] = None

  flow.add(EnsureNetwork(context.dst_cloud,
                         name = network_ensure,
                          rebind=[all_dst_networks, network_retrieve]))

  return flow, network_ensure


def list_ports(client) 
    # list_ports(fields=['network_id', 'mac_address', 'id'])
    try:
      return {
            'port_list': lambda: client.list_ports()["ports"]
      }
    except Exception as e:
      LOG.exception("Error in listing ports: %s" % e.message)
      raise

def del_port(client, port_id):
  try:
    return client.delete_port(port_id) 
  except Exception as e:
    LOG.exception("Error in delete port: %s, pord_id: %s" % (e.message, port_id) )
    raise

def create_port(client, network_id, mac, security_groups, ip_address): 
  port_params = {
    'network_id': network_id,
    'mac_address': mac,
    'security_groups': security_groups
  } 
  if (ip_address) 
    port_params['fixed_ips'] = [ { "ip_address": ip_address }  ] 

  # TODO Keyerror
  try:
    return client.create_port( {'port': port_params } )['port']  
  except Exception as e:
    LOG.exception("Error in create_port: %s, network_id: %s, mac: %s, ip_address: %s" % (e.message, network_id, mac, ip_address))
    raise 
  

def get_security_groups(client):
  try:
    return client.list_security_groups()['security_groups']
  except Exception as e:
    LOG.exception("Error in get security groups: %s" % e.message)
    raise

def del_security_groups(client, security_group):
  try:
    client.delete_security_group(security_group); 
  except Exception as e:
    LOG.exception("Error in get security groups: %s" % e.message)
    raise

def create_security_group(client, name, description) 
  try:
    return client.create_sequrity_group({
      "security_group": {  
        "name": name,
        "description": description
      }
    })
  except Exception as e:
    LOG.exception("Error in get security groups: %s" % e.message)
    raise


def list_subnets(client): 
  try:
    return client.list_subnets()['subnets']:
  except Exception as e:
    LOG.exception("Error in list subnets: %s" % e.message)
    raise

def del_subnet(client, subnet_id): 
  try:
    return client.list_subnets()['subnets']:
  except Exception as e:
    LOG.exception("Error in list subnets: %s" % e.message)
    raise

def create_subnet(client, network_name):
  try:
    return client.create_network({
      'network': network_name
    })
  except Exception as e:
    LOG.exception("Error in list subnets: %s" % e.message)
    raise

def list_network(client, network_info, tenant_id):
  try:
    if network_info:
      if 'id' in network_info:
        return client.list_networks(id=network_info['id'])['networks'][0]
      else if 'name' in network_info:
        return client.list_networks(name=network_info['name'])['networks'][0]
    else:
      return client.list_networks() 
  except Exception as e:
    LOG.exception("Error in get network: %s" % e.message)
    raise

