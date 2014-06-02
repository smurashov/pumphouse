Usage Scenario
==============

Pumphouse application is intended to be used by cloud operators or service
engineers to perform rolling upgrade of existing OpenStack-based cloud to
the Mirantis OpenStack cloud. Rolling upgrade means that the new cloud works on
the same set of hardware as original cloud. Workloads and resources are
gradually moved from the existing cloud to Mirantis OpenStack. Every physical
hypervisor node of the existing cloud eventually gets transferred to Miratnis
OpenStack and re-installed as it`s Compute node.

## Install pumphouse

Pumphouse is a python application and can be installed as a pip package:

```ShellSession
$ pip install pumphouse
```

## Acquire initial nodes

Optionally, pumphouse might allow to clean up nodes for Fuel deployment in the
existing cloud. This requires following steps:

- install pumphouse package
- use pumphouse to move virtual instances from certain nodes in existing cloud
  (via evacuate or live migrate or rebuild)
- move released bare metal nodes to isolated L2 network (VLAN) which will serve
  as Admin network from the standpoint of Fuel framework

## Install Fuel master node

We install Fuel master node on one of the nodes reserved for Mirantis OpenStack.
Mirantis OpenStack must be configured so it shares Private and Public L2 networks
with the existing OpenStack cluster.

![Pumphouse network diagram](doc/pumphouse-network-diagram.png)

In this diagram, components of source clouds are in purple, components of
Mirantis OpenStack cloud are in green, and shared Private and Public networks
are golden.

## Configure source and target clouds

Use configuration file pumphouse.yaml to configure source and target clouds:

```yml
  source:
    -
      name:     good_old_openstack
      auth_url: http://10.0.0.1:5000/v2.0/
      username: admin
      password: admin
      tenant:   admin
      token:    UUID
  target:
    -
      name:     mira-os-1
      auth_url: http://api.endpoint.com:5000/v2.0/
      fuel_url: http://127.0.0.1:8000/api/
      username: admin
      password: admin
```

You could configure multiple source and target clouds.

## Discover cloud

Given the auth URL and credentials, we could learn basic information about the
source and the destination clouds. Basic information includes the list of
services available in those clouds and URLs to API endpoints of those services.

We also could determine the list of resources in the source clouds, with their
parameters like UUIDs, names and resource type-specific attributes. We call this
process a discovery of resource.

Discovery of resource builds a dependency tree for this resource. This tree
includes all resources that must be present in the destination cloud before the
specified resource could be moved about.


## Workload moving cycle

Moving workloads from source cloud to Mirantis OpenStack cloud is a sequence of
moves of the individual resources executed in cycle. Operator must be able to
select workload resources they want to move. Resource might be as granular as
single VM, or it might be a whole tenant.

To migrate resources and nodes from the source cloud to Mirantis OpenStack, you
need to define what exactly you want to migrate. There are several possible
approaches to it:

- Define migration policy for every type of resource and then start migration
  process. The migration logic must recognize dependencies between resource
  types and move resources about accordingly. It also needs come error handling
  logic in case something goes wrong. This approach is only viable when you
  don't really care about the order of moving particular resources (beyond
  explicit dependencies between resource types).
- Manually inspect the cloud with standard tools like OpenStack dashboard or cli
  clients, determine which resources you want to move at this time and run
  migration scripts for that resources. Repeat that until you have all your
  resources in the new cloud. This approach allows you to precisely control the
  order of migration and the flow of migration itself (for example, handle
  non-standard errors). This is also useful when you only want to migrate the
  certain type of workloads (i.e. only a subset of all VMs in your source
  cloud).

To move stateless resource, one must move the virtual system image between
Glance services of clouds. Then VM on the source side must be stopped, metadata
from it (inlcuding IP addresses) must be copied to destination Mirantis
OpenStack cloud, and new VM must be instantiated from corresponding image.

This process should be repeated for all workloads that are being moved to
Mirantis OpenStack cloud.

## Migrate resources

Use standard OpenStack clients (installed as dependencies with `pumphouse`
package) to find and identify resources you`d like to migrate.

Use `pump-*` commands to migrate different resources (we refrain from using
`pump <subcommand>` format as `pump` command already used in
[distcc](https://code.google.com/p/distcc/)):

```ShellSession
$ pump-keystone tenants
$ pump-keystone roles
$ pump-keystone users [tenant]
$ pump-keystone user-roles
$ pump-nova instances <instance> [instance ...] | <host> | <tenant>
$ pump-nova networks [tenant]
$ pump-nova quotas [tenant]
$ pump-nova flavors
$ pump-nova keypairs [user]
$ pump-nova secgroups
$ pump-glance images [tenant]
```

- `<tenant>` tells the command to migrate only resources that belong to specific 
  tenant. Could be name or ID of the tenant.
- `instance` tells the command to move only specified instance. Could be name or
  ID of the instance
- `host` is a host name or IP address of hypervisor host. All resources from
  that host will be moved to the target cloud

## Transfer Compute nodes

Once all virtual instances from a compute node are moved to Mirantis OpenStack
cloud, that compute node should be decomissioned from source cloud and
re-installed as compute node in Mirantis OpenStack cluster.

Following steps should be performed:

- disable the compute node in source OpenStack cloud
- shutdown the node using IPMI interface
- move node's port to Admin VLAN of Mirantis OpenStack
- power up the node using IPMI interface
- boot the node from Fuel master node via PXE
- assign Compute role to the node via Fuel API
- deploy the node as Compute node in Mirantis OpenStack cluster via Fuel

Use `nova hypervisor-list`, `nova hypervisor-show` commands to identify which
hosts are cleansed from all workload. To decomission host from the existing
cloud and move it to Mirantis OpenStack, use `pump-host` command:

```ShellSession
$ pump-nova host <hostname> [hostname ...]
```

As a result, host `<hostname>` will be powered down, rewired to isolated Admin
network and powered up. Then the host will boot via PXE from Fuel node, register
in Fuel as a compute node. Finally, operating systeme and OpenStack services
will be deployed on it.

### Decomission source cloud

If the ultimate goal of the migration process is to completely replace existing
OpenStack infrastructure with Mirantis OpenStack, then as a final step of the
move controllers of the source cloud should be decomissioned and added to
Mirantis OpenStack cluster.

Steps for decomissioning the controller node are generally the same as steps to
move compute node from source to destination cluster.
