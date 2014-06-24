import argparse
import logging
import os
import pyipmi
import pyipmi.bmc
import time
import urllib2
import yaml

from operator import attrgetter


LOG = logging.getLogger(__name__)

SOURCE_CLOUD_TAG = 'source'
FUEL_MASTER_NODE_TAG = 'fuel.master'
FUEL_API_IFACE_TAG = 'fuel.api'
DEFAULT_INVENTORY_FILE='inventory.yaml'


class Error(Exception):
    pass


class NotFound(Error):
    pass


class TimeoutException(Error):
    pass


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f.read())


def get_parser():
    parser = argparse.ArgumentParser(description="Migrates physical servers from "
                                                 "OpenStack cloud to Mirantis "
                                                 "OpenStack cloud.")
    parser.add_argument("-i", "--inventory",
                        default=None,
                        type=safe_load_yaml,
                        help="A filename of an inventory of datacenter "
                             "hardware")
    parser.add_argument("-e", "--env-id",
                        default=1,
                        type=int,
                        help="An ID of target Mirantis OpenStack cloud in Fuel")
    parser.add_argument("hostname",
                        type=str,
                        help="A host reference of server to migrate as appears "
                        "in the 'hosts' section in INVENTORY file")
    return parser


def read_configuration(stream):
    with stream as f:
        return yaml.safe_load(f.read())


def get_bmc(ipmi):
    host = ipmi['host']
    username = ipmi['auth']['user']
    password = ipmi['auth']['password']
    bmc = pyipmi.make_bmc(pyipmi.bmc.LanBMC,
                          hostname=host,
                          username=username,
                          password=password)
    return bmc


def force_pxeboot(host):
    host = get_bmc(host['ipmi'])
    try:
        host.set_bootdev('pxe')
    except Exception as exc:
        LOG.exception("Cannot set boot device to PXE: %s", exc.message)
    try:
        host.set_chassis_power('reset')
    except Exception as exc:
        LOG.exception("Cannot reset host %s: %s",
                      host['ipmi']['host'],
                      exc.message)


def get_fuel_endpoint(config):
    for host_ref in config['hosts']:
        host = config['hosts'][host_ref]
        if FUEL_MASTER_NODE_TAG in host['notes']:
            fuel_master = host
    for iface_ref in fuel_master['interfaces']:
        iface = fuel_master['interfaces'][iface_ref]
        if FUEL_API_IFACE_TAG in iface['tags']:
            endpoint = iface['ip'][0]
    return endpoint


class Fuel(object):

    '''Fuel interface class

    :param endpoint:    IP address of Fuel master node
    :param env_id:      ID of environment for target Mirantis OpenStack cluster
    :type env_id:       int
    '''

    def __init__(self, endpoint, env_id):
        os.environ['LISTEN_ADDRESS'] = endpoint
        from fuelclient.objects.environment import Environment
        self.env = Environment(env_id)

    def assign_role(self, node, role='compute'):

        '''Deploy compute node to Mirantis OpenStack cluster via Fuel API

        This function adds a host to Mirantis OpenStack cluster as a Compute node.
        It finds node defined by its ID in Fuel API, verifies that it is in
        'discover' status and assigns 'compute' role to it.

        :param node:        Fuel Node object to assign role to
        :param role:        role to assign to the node, defaults to 'compute'
        '''
        node.update()
        if node.data['status'] == 'discover':
            self.env.assign((node,), (role,))
            LOG.info("Assigned role: %s", node.data)
        elif node.data['status'] == 'error':
            LOG.exception("Node in 'error' status: %s", node.data)
            raise Error
        else:
            LOG.warn("Node already added: %s", node.data)

    def get_next_id(self):
        next_id = sorted(self.env.get_all_nodes(), key=attrgetter('id'))[-1].id + 1
        return next_id

    def wait_for_node(self, status, node_id, timeout=300):
        from fuelclient.objects.node import Node
        node = Node(node_id)
        start_time = time.clock()
        while time.clock() < (start_time + timeout):
            try:
                node.update()
            except urllib2.HTTPError as exc:
                if exc.code == 404:
                    sleep(5)
                else:
                    LOG.exception("Exception while waiting for node: %s",
                                  exc.message)
                    raise exc
            else:
                if node.data['status'] == status:
                    LOG.info("Node in %s status: %s", status, node.data)
                    return node
                elif node.data['status'] == 'error'
                    LOG.exception("Node in 'error' status: %s", node.data)
                    raise Error
        else:
            LOG.exception("Timed out while waiting for node: %s",
                    node_id)
            raise TimeoutException


def main():
    parser = get_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    env_id = args.env_id
    hostname = args.hostname
    if args.inventory is not None:
        inventory = args.inventory
    else:
        inventory = safe_load_yaml(DEFAULT_INVENTORY_FILE)
    fuel_endpoint = get_fuel_endpoint(inventory)
    inventory_host = inventory['hosts'][hostname]

    if SOURCE_CLOUD_TAG not in inventory_host['notes']:
        LOG.exception("Host not in source cloud: %s", inventory_host)
        raise Error

    fuel = Fuel(fuel_endpoint, env_id)
    node_id = fuel.get_next_id()
    force_pxeboot(inventory_host)
    node = fuel.wait_for_node('discover', node_id)
    fuel.assign_role(node)
    try:
        task = fuel.env.deploy_changes()
    except urllib2.HTTPError as exc:
        LOG.exception("Cannot deploy changes: %s", exc.code)
        raise Error
    node = fuel.wait_for_node('ready', node_id, 3600)
    LOG.info("Node deployed: %s", node.data)


if __name__ == "__main__":
    main()
