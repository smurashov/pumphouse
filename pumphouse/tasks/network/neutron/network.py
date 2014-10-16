import logging

from taskflow.patterns import linear_flow

from pumphouse import task
from pumphouse import events
from pumphouse import exceptions
from pumphouse.tasks import utils as task_utils

# TODO (sryabin) create|del|list_security_group_rule implementation

def list_ports(self, client) 
    # list_ports(fields=['network_id', 'mac_address', 'id'])
    try:
      return {
            'port_list': lambda: client.list_ports()["ports"]
      }
    except Exception as e:
      LOG.exception("Error in listing ports: %s" % e.message)
      raise

def del_port(self, client, port_id):
  try:
    return client.delete_port(port_id) 
  except Exception as e:
    LOG.exception("Error in delete port: %s, pord_id: %s" % (e.message, port_id) )
    raise

def create_port(self, client, network_id, mac, security_groups, ip_address): 
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
  

def get_security_groups(self, client):
  try:
    return client.list_security_groups()['security_groups']
  except Exception as e:
    LOG.exception("Error in get security groups: %s" % e.message)
    raise

def del_security_groups(self, client, security_group):
  try:
    client.delete_security_group(security_group); 
  except Exception as e:
    LOG.exception("Error in get security groups: %s" % e.message)
    raise

def create_security_group(self, client, name, description) 
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


def list_subnets(self, client): 
  try:
    return client.list_subnets()['subnets']:
  except Exception as e:
    LOG.exception("Error in list subnets: %s" % e.message)
    raise

def del_subnet(self, client, subnet_id): 
  try:
    return client.list_subnets()['subnets']:
  except Exception as e:
    LOG.exception("Error in list subnets: %s" % e.message)
    raise

def create_subnet(self, client, network_name):
  try:
    return client.create_network({
      'network': network_name
    })
  except Exception as e:
    LOG.exception("Error in list subnets: %s" % e.message)
    raise

def list_network(self, client, network_info, tenant_id):
  try:
    if 'id' in network_info:
      return client.list_networks(id=network_info['id'])['networks'][0]
    if 'name' in network_info:
      return client.list_networks(name=network_info['name'])['networks'][0]
  except Exception as e:
    LOG.exception("Error in get network: %s" % e.message)
    raise
