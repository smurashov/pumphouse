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
from pumphouse import flows
from pumphouse.tasks import service as service_tasks
from pumphouse import task as pump_task
from pumphouse import utils


LOG = logging.getLogger(__name__)

assignment = flows.register("assignment", default="fixed")


# NOTE(akscram): Here we should transform FQDNs of nodes to
#                hostnames of Nova hypervisors.
def extract_hostname(info):
    # XXX(akscram): There is no the fqdn attribute in node with
    #               `discover` status.
    if info["fqdn"] is None:
        hostname = "node-{}.domain.tld".format(info["id"])
    else:
        hostname = info["fqdn"]
    return hostname


def extract_macs(info):
    macs = set(i["mac"] for i in info["meta"]["interfaces"])
    return tuple(macs)


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
        nodes = dict((extract_hostname(node.data), node.data)
                     for node in env.get_all_nodes())
        return nodes


class RetrieveNode(task.Task):
    def execute(self, nodes_infos, hostname):
        return nodes_infos[hostname]


class DeployChanges(pump_task.BaseCloudTask):
    def execute(self, env_info, **nodes_infos):
        from pumphouse._vendor.fuelclient.objects import environment
        env = environment.Environment.init_with_data(env_info)
        task = env.deploy_changes()
        watched_macs = set(extract_macs(node_info)
                           for node_info in nodes_infos.itervalues())
        for progress, nodes in task:
            for node in nodes:
                node_macs = extract_macs(node.data)
                if node_macs in watched_macs:
                    self.provisioning_event(progress, node)
        env.update()
        return env.data

    def revert(self, env_info, result, flow_failures, **nodes_infos):
        LOG.error("Deploying of changes failed for env %r with result %r",
                  env_info, result)

    def provisioning_event(self, progress, node):
        LOG.debug("Waiting for deploy: %r, %r", progress, node)
        events.emit("update", {
            "id": extract_hostname(node.data),
            "type": "host",
            "cloud": self.cloud.name,
            "progress": node.data["progress"],
            "data": {
                "status": node.data["status"],
            }
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


class ExtractDisksFromNode(task.Task):
    def execute(self, node_info):
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        disks = node.get_attribute("disks")
        return [{
            "name": d["name"],
            "size": d["size"],
            "volumes": d["volumes"],
        } for d in disks]


class ExtractIfacesFromNode(task.Task):
    def execute(self, node_info):
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        ifaces = node.get_attribute("interfaces")
        return [{
            "name": i["name"],
            "assigned_networks": i["assigned_networks"],
        } for i in ifaces]


class ExtractNetworkDataFromEnv(task.Task):
    def execute(self, env_info):
        from pumphouse._vendor.fuelclient.objects import environment
        env = environment.Environment.init_with_data(env_info)
        network_data = env.get_network_data()
        return network_data


class PopulateIfacesWithIDs(task.Task):
    def execute(self, network_data, ifaces):
        ifaces_ids = {n["name"]: n["id"] for n in network_data["networks"]}
        ifaces_with_ids = [{
            "name": i["name"],
            "assigned_networks": [{
                "id": ifaces_ids[a],
                "name": a,
            } for a in i["assigned_networks"]],
        } for i in ifaces]
        return ifaces_with_ids


class ApplyDisksAttributesFromNode(task.Task):
    def execute(self, disks, node_info):
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)

        node_disks = node.get_attribute("disks")
        changed_disks = self.update_disks_attrs(disks, node_disks)
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


class ApplyNetAttributesFromNode(task.Task):
    def execute(self, ifaces, node_info):
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)

        node_ifaces = node.get_attribute("interfaces")
        changed_ifaces = self.update_ifaces_attrs(ifaces, node_ifaces)
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
        condition_check = lambda x: x is not None
        node_macs = extract_macs(node_info)
        unassigned_node_info = utils.wait_for(node_macs,
                                              self.retrieve_unassigned,
                                              attribute_getter=condition_check,
                                              value=True,
                                              timeout=360)
        return unassigned_node_info

    def retrieve_unassigned(self, node_macs):
        from pumphouse._vendor.fuelclient.objects.node import Node
        for node in Node.get_all():
            if (node.data["status"] == "discover" and
                    extract_macs(node.data) == node_macs):
                return node.data
        # TODO(akscram): Raise an exception when status is error.
        return None


class UnassignNode(pump_task.BaseCloudTask):
    def execute(self, node_info, env_info):
        from pumphouse._vendor.fuelclient.objects import environment
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        env = environment.Environment.init_with_data(env_info)
        env.unassign((node.id,))
        node.update()
        self.unassign_start_event(node)
        return node.data

    def unassign_start_event(self, node):
        events.emit("update", {
            "id": extract_hostname(node.data),
            "cloud": self.cloud.name,
            "type": "host",
            "action": "reassignment",
        }, namespace="/events")


class HostsDeleteEvents(pump_task.BaseCloudTask):
    def execute(self, services):
        # XXX(akscram): Here can be emited some number of unexpected events.
        for service in services:
            if service["binary"] == "nova-compute":
                self.delete_event(service)

    def delete_event(self, service):
        events.emit("delete", {
            "id": service["host"],
            "cloud": self.cloud.name,
            "type": "host",
        }, namespace="/events")


class AssignNode(pump_task.BaseCloudTask):
    def execute(self, node_info, node_roles, env_info):
        from pumphouse._vendor.fuelclient.objects import environment
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        env = environment.Environment.init_with_data(env_info)
        env.assign((node,), node_roles)
        node.update()
        self.assign_start_event(node)
        return node.data

    def assign_start_event(self, node):
        hostname = extract_hostname(node.data)
        events.emit("create", {
            "id": hostname,
            "cloud": self.cloud.name,
            "type": "host",
            "action": "reassignment",
            "data": {
                "name": hostname,
            }
        }, namespace="/events")


class UpdateNodeInfo(task.Task):
    def execute(self, node_info, **requires):
        from pumphouse._vendor.fuelclient.objects.node import Node
        node = Node.init_with_data(node_info)
        node.update()
        return node.data


class GetNodeHostname(task.Task):
    def execute(self, node_info):
        hostname = extract_hostname(node_info)
        return hostname


class HostsSuccessEvents(pump_task.BaseCloudTask):
    def execute(self, services):
        # XXX(akscram): Here can be emited some number of unexpected events.
        for service in services:
            self.update_event(service)

    def update_event(self, service):
        events.emit("update", {
            "id": service["host"],
            "cloud": self.cloud.name,
            "type": "host",
            "progress": None,
            "action": None,
        }, namespace="/events")


def unassign_node(context, flow, env_name, hostname):
    env = "src-env-{}".format(env_name)
    deployed_env = "src-env-deployed-{}".format(env_name)
    env_nodes = "src-env-nodes-{}".format(env_name)
    node = "node-{}".format(hostname)
    pending_node = "node-pending-{}".format(hostname)
    unassigned_node = "node-unassigned-{}".format(hostname)

    flow.add(
        RetrieveEnvNodes(name=env_nodes,
                         provides=env_nodes,
                         rebind=[env]),
        RetrieveNode(name=node,
                     provides=node,
                     rebind=[env_nodes],
                     inject={"hostname": hostname}),
        UnassignNode(context.src_cloud,
                     name=pending_node,
                     provides=pending_node,
                     rebind=[node, env]),
        DeployChanges(context.src_cloud,
                      name=deployed_env,
                      provides=deployed_env,
                      rebind=[env],
                      requires=[pending_node]),
        WaitUnassignedNode(name=unassigned_node,
                           provides=unassigned_node,
                           rebind=[pending_node],
                           requires=[deployed_env]),
    )


class DeleteServicesFromNode(service_tasks.DeleteServicesSilently):
    def execute(self, node_info, **requires):
        hostname = extract_hostname(node_info)
        return super(DeleteServicesFromNode, self).execute(hostname)


def remove_computes(context, flow, env_name, hostname):
    deployed_env = "src-env-deployed-{}".format(env_name)
    pending_node = "node-pending-{}".format(hostname)
    delete_services = "services-delete-{}".format(hostname)
    delete_services_events = "services-delete-events-{}".format(hostname)

    flow.add(
        DeleteServicesFromNode(context.src_cloud,
                               name=delete_services,
                               provides=delete_services,
                               rebind=[pending_node],
                               inject={"hostname": hostname},
                               requires=[deployed_env]),
        HostsDeleteEvents(context.src_cloud,
                          name=delete_services_events,
                          rebind=[delete_services]),
    )


@assignment.add("discovery")
def assignment_discovery(context, flow, env_name, hostname):
    env = "dst-env-{}".format(env_name)
    env_nodes = "dst-env-nodes-{}".format(env_name)
    compute_node = "node-compute-{}".format(env_name)

    compute_roles = "compute-roles-{}".format(env_name)
    compute_disks = "compute-disks-{}".format(env_name)
    compute_ifaces = "compute-ifaces-{}".format(env_name)

    flow.add(
        RetrieveEnvNodes(name=env_nodes,
                         provides=env_nodes,
                         rebind=[env]),
        ChooseAnyComputeNode(name=compute_node,
                             provides=compute_node,
                             rebind=[env_nodes, env]),
        ExtractRolesFromNode(name=compute_roles,
                             provides=compute_roles,
                             rebind=[compute_node]),
        ExtractDisksFromNode(name=compute_disks,
                             provides=compute_disks,
                             rebind=[compute_node]),
        ExtractIfacesFromNode(name=compute_ifaces,
                              provides=compute_ifaces,
                              rebind=[compute_node]),
    )


@assignment.add("fixed")
def assignment_fixed(context, flow, env_name, hostname):
    env = "dst-env-{}".format(env_name)
    env_network = "dst-env-network-{}".format(env_name)

    compute_roles = "compute-roles-{}".format(env_name)
    compute_disks = "compute-disks-{}".format(env_name)
    compute_ifaces = "compute-ifaces-{}".format(env_name)

    params = context.config["assignment_parameters"]

    context.store.update({
        compute_roles: params["roles"],
        compute_disks: params["disks"],
    })
    flow.add(
        ExtractNetworkDataFromEnv(name=env_network,
                                  provides=env_network,
                                  rebind=[env]),
        PopulateIfacesWithIDs(name=compute_ifaces,
                              provides=compute_ifaces,
                              rebind=[env_network],
                              inject={"ifaces": params["ifaces"]}),
    )


def assign_node(context, flow, env_name, hostname):
    env = "dst-env-{}".format(env_name)
    deployed_env = "dst-env-deployed-{}".format(env_name)
    env_nodes = "dst-env-nodes-{}".format(env_name)

    unassigned_node = "node-unassigned-{}".format(hostname)
    assigned_node = "node-assigned-{}".format(hostname)

    compute_roles = "compute-roles-{}".format(env_name)
    compute_disks = "compute-disks-{}".format(env_name)
    compute_ifaces = "compute-ifaces-{}".format(env_name)

    node_with_disks = "node-with-disks-{}".format(hostname)
    node_with_nets = "node-with-nets-{}".format(hostname)

    flow.add(
        AssignNode(context.dst_cloud,
                   name=assigned_node,
                   provides=assigned_node,
                   rebind=[unassigned_node, compute_roles, env]),
        ApplyDisksAttributesFromNode(name=node_with_disks,
                                     provides=node_with_disks,
                                     rebind=[compute_disks, assigned_node]),
        ApplyNetAttributesFromNode(name=node_with_nets,
                                   provides=node_with_nets,
                                   rebind=[compute_ifaces, assigned_node]),
        DeployChanges(context.dst_cloud,
                      name=deployed_env,
                      provides=deployed_env,
                      rebind=[env],
                      requires=[node_with_disks, node_with_nets]),
    )


def wait_computes(context, flow, env_name, hostname):
    deployed_env = "dst-env-deployed-{}".format(env_name)
    assigned_node = "node-assigned-{}".format(hostname)
    updated_assigned_node = "node-assigned-updated-{}".format(hostname)
    assigned_node_hostname = "node-assigned-hosetname-{}".format(hostname)
    wait_computes = "wait-computes-{}".format(hostname)
    host_success_events = "node-success-events-{}".format(hostname)

    flow.add(
        UpdateNodeInfo(name=updated_assigned_node,
                       provides=updated_assigned_node,
                       rebind=[assigned_node],
                       requires=[deployed_env]),
        GetNodeHostname(name=assigned_node_hostname,
                        provides=assigned_node_hostname,
                        rebind=[updated_assigned_node]),
        service_tasks.WaitComputesServices(context.dst_cloud,
                                           name=wait_computes,
                                           provides=wait_computes,
                                           rebind=[assigned_node_hostname],
                                           requires=[deployed_env]),
        HostsSuccessEvents(context.dst_cloud,
                           name=host_success_events,
                           rebind=[wait_computes]),
    )


def reassign_node(context, hostname):
    src_env_name = context.config["source"]
    dst_env_name = context.config["destination"]

    envs = "all-environments"
    src_env = "src-env-{}".format(src_env_name)
    dst_env = "dst-env-{}".format(dst_env_name)
    src_env_nodes = "src-env-nodes-{}".format(src_env_name)

    flow = graph_flow.Flow(name="reassign-node-{}".format(hostname))
    flow.add(
        RetrieveAllEnvironments(name=envs,
                                provides=envs),
        # Source
        RetrieveEnvironment(name=src_env,
                            provides=src_env,
                            rebind=[envs],
                            inject={"env_name": src_env_name}),
        # Destination
        RetrieveEnvironment(name=dst_env,
                            provides=dst_env,
                            rebind=[envs],
                            inject={"env_name": dst_env_name}),
    )
    unassign_node(context, flow, src_env_name, hostname)
    remove_computes(context, flow, src_env_name, hostname)
    assignment(context, flow, dst_env_name, hostname)
    assign_node(context, flow, dst_env_name, hostname)
    wait_computes(context, flow, dst_env_name, hostname)
    return flow
