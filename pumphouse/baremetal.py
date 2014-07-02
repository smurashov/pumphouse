import logging
import operator
import os
import time
import urllib2
import yaml

import pyipmi
import pyipmi.bmc


LOG = logging.getLogger(__name__)


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

        This function adds a host to Mirantis OpenStack cluster as a Compute
        node.
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

    def wait_for_node(self, status='discover', node_id=0, timeout=300):
        from fuelclient.objects.node import Node
        node = Node(node_id)
        start_time = time.clock()
        while time.clock() < (start_time + timeout):
            if not node_id:
                node = sorted(node.get_all(),
                              key=operator.attrgetter('id'),
                              reverse=True)[0]
                if not node.data['cluster']:
                    return node
                else:
                    continue
            try:
                node.update()
            except urllib2.HTTPError as exc:
                if exc.code == 404:
                    LOG.info("Waiting for node discovery: %s". node_id)
                    time.sleep(5)
                else:
                    LOG.exception("Exception while waiting for node: %s",
                                  exc.message)
                    raise exc
            else:
                if node.data['status'] == status:
                    LOG.info("Node in %s status: %s", status, node.data)
                    return node
                elif node.data['status'] == 'error':
                    LOG.exception("Node in 'error' status: %s", node.data)
                    raise Error
        else:
            LOG.exception("Timed out while waiting for node: %s",
                          node_id)
            raise TimeoutException


class IPMI(object):
    """IPMI interface class

    This class allows to manage the host via IPMI protocol. It could be
    instantiated from dictionary with class method from_dict, for example:

        host = {
                'host': '10.0.0.1',
                'auth':
                {
                    'user': 'admin',
                    'password': 'pass'
                }
               }
        ipmi = IPMI.from_dict(host)

    :param host:        name or address of the IPMI controller
    :param username:    auth user name of admin of IPMI controller
    :param password:    auth password for the admin user of IPMI controller
    """

    def __init__(self, host, username, password):
        self.hostname = host
        self.username = username
        self.password = password
        self.client = pyipmi.make_bmc(pyipmi.bmc.LanBMC,
                                      hostname=self.host,
                                      usernmae=self.username,
                                      password=self.password)

    @classmethod
    def from_dict(cls, ipmi_dict):
        hostname = ipmi_dict["host"]
        username = ipmi_dict["auth"]["user"]
        password = ipmi_dict["auth"]["password"]
        return cls(hostname, username, password)

    def force_pxeboot(self):
        try:
            self.client.set_bootdev('pxe')
        except Exception as exc:
            LOG.exception("Cannot set boot device to PXE: %s", exc.message)
        try:
            self.client.set_chassis_power('reset')
        except Exception as exc:
            LOG.exception("Cannot reset host %s: %s",
                          self.host,
                          exc.message)
