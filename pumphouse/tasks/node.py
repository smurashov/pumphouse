# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.


import logging

from taskflow.patterns import graph_flow
from taskflow import task

from pumphouse import events
from pumphouse import exceptions
from pumphouse import utils


LOG = logging.getLogger(__name__)


# NOTE(akscram): Here we should transform FQDNs of nodes to
#                hostnames of Nova hypervisors.
def extract_hostname(fqdn):
    hostname, _, _ = fqdn.partition(".")
    return hostname


class RetrieveAllEnvironments(task.Task):
    def execute(self):
        from pumphouse._vendor.fuelclient.objects import environment
        envs = dict((env.data["name"], env.data)
                    for env in environment.Environment.get_all())
        return envs


class RetrieveEnvironment(task.Task):
    def execute(self, envs_infos, env_name):
        return envs_infos[env_name]


class RetrieveEnvNodes(task.Task):
    def execute(self, env_info):
        from pumphouse._vendor.fuelclient.objects import environment
        env = environment.Environment.init_with_data(env_info)
        nodes = dict((extract_hostname(node.data["fqdn"]), node.data)
                     for node in env.get_all_nodes())
        return nodes


class RetrieveNode(task.Task):
    def execute(self, nodes_infos, hostname):
        return nodes_infos[hostname]


class DeployChanges(task.Task):
    def execute(self, env_info, **nodes_infos):
        from pumphouse._vendor.fuelclient.objects import environment
        env = environment.Environment.init_with_data(env_info)
        task = env.deploy_changes()
        watched_fqdns = set(node_info["fqdn"]
                            for node_info in nodes_infos.itervalues())
        for progress, nodes in task:
            for node in nodes:
                if node.data["fqdn"] in watched_fqdns:
                    self.provisioning_event(progress, node)
        env.update()
        return env.data

    def revert(self, env_info, result, flow_failures, **nodes_infos):
        LOG.error("Deploying of changed failed for env %r with result %r",
                  env_info, result)

    def provisioning_event(self, progress, node):
        LOG.debug("Waiting for deploy: %r, %r", progress, node)
        events.emit("host provisioning", {
            "id": extract_hostname(node.data["fqdn"]),
            "status": node.data["status"],
            "progress": node.data["progress"],
        }, namespace="/events")


class ChooseAnyComputeNode(task.Task):
    def execute(self, nodes_infos, env_info):
        # XXX(akscram): The source of the configuration is the first
        #               node with the `compute` role.
        compute_nodes = [info
                         for info in nodes_infos.values()
                         if "compute" in info["roles"]]
        if not compute_nodes:
            raise exceptions.Conflict("There is no any compute nodes in "
                                      "environment %r" % (env_info,))
        compute_node = compute_nodes[0]
        return compute_node


class ExtractRolesFromNode(task.Task):
    def execute(self, node_info):
        return node_info["roles"]


class CopyDisksAttributesFromNode(task.Task):
    def execute(self, from_node_info, node_info):
        from pumphouse._vendor.fuelclient.objects.node import Node
        from_node = Node.init_with_data(from_node_info)
        node = Node.init_with_data(node_info)

        from_disks = from_node.get_attribute("disks")
        disks = node.get_attribute("disks")
        changed_disks = self.update_disks_attrs(from_disks, disks)
        node.upload_node_attribute("disks", changed_disks)

        node.update()
        return node.data

    def update_disks_attrs(self, disks1, disks2):
        """Updates geometries of partitions.

        Returns a new dict which is made from elements from disk2 with
        geometry of partitions from disk1.
        """

        def to_dict(attrs):
            return dict((attr["name"], attr) for attr in attrs)

        attrs = []
        disks_dict1 = to_dict(disks1)
        for disk in disks2:
            volumes = [{"name": v["name"],
                        "size": v["size"]}
                       for v in disks_dict1[disk["name"]]["volumes"]]
            attrs.append({
                "id": disk["id"],
                "size": disk["size"],
                "volumes": volumes,
            })
        return attrs


class CopyNetAttributesFromNode(task.Task):
    def execute(self, from_node_info, node_info):
        from pumphouse._vendor.fuelclient.objects.node import Node
        from_node = Node.init_with_data(from_node_info)
        node = Node.init_with_data(node_info)

        from_ifaces = from_node.get_attribute("interfaces")
        ifaces = node.get_attribute("interfaces")
        changed_ifaces = self.update_ifaces_attrs(from_ifaces, ifaces)
        node.upload_node_attribute("interfaces", changed_ifaces)

        node.update()
        return node.data

    def update_ifaces_attrs(self, ifaces1, ifaces2):
        """Updates configuration of network interfaces.

        Returns a new dict which is made from elements from ifaces2
        with assignments from ifaces1.
        """
        def to_dict(attrs):
            return dict((attr["name"], attr) for attr in attrs)

        attrs = []
        ifaces_dict1 = to_dict(ifaces1)
        for iface in ifaces2:
            attrs.append({
                "id": iface["id"],
                "type": iface["type"],
                "assigned_networks":
                    ifaces_dict1[iface["name"]]["assigned_networks"],
            })
        return attrs


class WaitUnassignedNode(task.Task):
    def execute(self, node_info, **requires):
        node_data = self.retirieve_unassigned(node_info)
        condition_check = lambda x: x is not None
        unassigned_node_info = utils.wait_for(node_info,
                                              self.retirieve_unassigned,
                                              attribute_getter=condition_check,
                                              value=True,
                                              timeout=360)
        return unassigned_node_info

    def retirieve_unassigned(self, node_info):
        def extract_macs(info):
            macs = set(i["mac"] for i in info["meta"]["interfaces"])
            return macs

        from pumphouse._vendor.fuelclient.objects.node import Node
        node_macs = extract_macs(node_info)
        for node in Node.get_all():
            if (node.data["status"] == "discover" and
                    node_macs == extract_macs(node.data)):
                return node.data
        # TODO(akscram): Raise an exception when status is error.
        return None


class UnassignNode(task.Task):
    def execute(self, node_info, env_info):
        from pumphouse._vendor.fuelclient.objects import environment
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        env = environment.Environment.init_with_data(env_info)
        env.unassign((node.id,))
        node.update()
        return node.data


class AssignNode(task.Task):
    def execute(self, node_info, node_roles, env_info):
        from pumphouse._vendor.fuelclient.objects import environment
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        env = environment.Environment.init_with_data(env_info)
        env.assign((node,), node_roles)
        node.update()
        return node.data


def unassign_node(context, flow, env_name, hostname):
    env = "src-env-{}".format(env_name)
    deployed_env = "src-env-deployed-{}".format(env_name)
    env_nodes = "src-env-nodes-{}".format(env_name)
    node = "node-{}".format(hostname)
    pending_node = "node-pending-{}".format(hostname)
    unassigned_node = "node-unassigned-{}".format(hostname)

    flow.add(
        RetrieveNode(name=node,
                     provides=node,
                     rebind=[env_nodes],
                     inject={"hostname": hostname}),
        UnassignNode(name=pending_node,
                     provides=pending_node,
                     rebind=[node, env]),
        DeployChanges(name=deployed_env,
                      provides=deployed_env,
                      rebind=[env],
                      requires=[pending_node]),
        WaitUnassignedNode(name=unassigned_node,
                           provides=unassigned_node,
                           rebind=[pending_node],
                           requires=[deployed_env]),
    )


def assign_node(context, flow, env_name, hostname):
    env = "dst-env-{}".format(env_name)
    deployed_env = "dst-env-deployed-{}".format(env_name)
    env_nodes = "dst-env-nodes-{}".format(env_name)
    unassigned_node = "node-unassigned-{}".format(hostname)
    assigned_node = "node-assigned-{}".format(hostname)
    compute_node = "node-compute-{}".format(env_name)
    compute_roles = "compute-roles-{}".format(env_name)
    node_with_disks = "node-with-disks-{}".format(hostname)
    node_with_nets = "node-with-nets-{}".format(hostname)

    flow.add(
        ChooseAnyComputeNode(name=compute_node,
                             provides=compute_node,
                             rebind=[env_nodes, env]),
        ExtractRolesFromNode(name=compute_roles,
                             provides=compute_roles,
                             rebind=[compute_node]),
        AssignNode(name=assigned_node,
                   provides=assigned_node,
                   rebind=[unassigned_node, compute_roles, env]),
        CopyDisksAttributesFromNode(name=node_with_disks,
                                    provides=node_with_disks,
                                    rebind=[compute_node, assigned_node]),
        CopyNetAttributesFromNode(name=node_with_nets,
                                  provides=node_with_nets,
                                  rebind=[compute_node, assigned_node]),
        DeployChanges(name=deployed_env,
                      provides=deployed_env,
                      rebind=[env],
                      requires=[node_with_disks, node_with_nets]),
    )


def reassign_node(context, hostname):
    src_env_name = context.config["source"]
    dst_env_name = context.config["destination"]

    envs = "all-environments"
    src_env = "src-env-{}".format(src_env_name)
    dst_env = "dst-env-{}".format(dst_env_name)
    src_env_nodes = "src-env-nodes-{}".format(src_env_name)
    dst_env_nodes = "dst-env-nodes-{}".format(dst_env_name)

    flow = graph_flow.Flow(name="reassign-node-{}".format(hostname))
    flow.add(
        RetrieveAllEnvironments(name=envs,
                                provides=envs),
        # Source
        RetrieveEnvironment(name=src_env,
                            provides=src_env,
                            rebind=[envs],
                            inject={"env_name": src_env_name}),
        RetrieveEnvNodes(name=src_env_nodes,
                         provides=src_env_nodes,
                         rebind=[src_env]),
        # Destination
        RetrieveEnvironment(name=dst_env,
                            provides=dst_env,
                            rebind=[envs],
                            inject={"env_name": dst_env_name}),
        RetrieveEnvNodes(name=dst_env_nodes,
                         provides=dst_env_nodes,
                         rebind=[dst_env]),
    )
    unassign_node(context, flow, src_env_name, hostname)
    assign_node(context, flow, dst_env_name, hostname)
    return flow
