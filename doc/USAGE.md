Usage Scenario
==============

Pumphouse application is intended to be used by cloud operators or service
engineers to perform rolling upgrade of existing OpenStack-based cloud to
the Mirantis OpenStack. Rolling upgrade means that the new OpenStack
installation works on the same set of hardware as original cloud. Workloads and
resources are gradually moved from the existing cloud to Mirantis OpenStack.
Every physical hypervisor node of the existing cloud eventually gets added to
Miratnis OpenStack and re-installed as it`s Compute node.

## Install pumphouse

Pumphouse is a python application and can be installed as a pip package:

```ShellSession
$ pip install pumphouse
```

## Acquire initial nodes

Optionally, pumphouse might allow to clean up nodes for Fuel deployment in the
existing cloud. This requires following steps:

- install pumphouse package onto a node that has access to following networks:
  *public/management API network* of Source cloud; *IPMI management network* of
  Source cloud.
- use pumphouse to move virtual instances from certain nodes in existing cloud
  (via evacuate or live migrate or rebuild)
- move released bare metal nodes to isolated L2 network (VLAN) which will serve
  as Admin network for Fuel deployment framework

## Install Fuel master node

We install Fuel master node on one of the nodes reserved for Mirantis OpenStack.
Mirantis OpenStack must be configured so it shares Private and Public L2 networks
with the existing OpenStack cluster.

![Pumphouse network diagram](pumphouse-network-diagram.png)

In this diagram, components of source clouds are in purple, components of
Mirantis OpenStack cloud are in green, and shared Private and Public networks
are golden.

## Configure source and target clouds

Use configuration file `config.yaml` to configure source and target clouds, see
example in `samples/config.yaml`

## Discover cloud

Given the auth URL and credentials, we could learn basic information about the
source and the destination clouds. Basic information includes the list of
services available in those clouds and URLs to API endpoints of those services.

## Moving workloads

We need to migrate workloads and virtual resources associated with them from
(arbitrary) custom OpenStack cloud to the cloud based on the latest release of
Mirantis OpenStack platform.

Migration must be as seamless as possible, with minimal downtime for workload
being migrated.

Operators must be able to select workload resources they want to move based on
different grouping criteria. The exact criteria depend on the type of resource
being moved about. See details on migration strategies in
[RESOURCES](RESOURCES.md) document.

## Migrate resources

Use standard OpenStack clients (installed as dependencies with `pumphouse`
package) to find and identify resources you`d like to migrate. 

In version 0.1, you can use `migration.py` script to move resources about. See
usage details in [`scripts/README.md`](../scripts/README.md) file.

In future versions, we will implement subcommands-based CLI for atomic
operations and Web-based UI.

## Prepare host for upgrade

We need to upgrade the whole customer's OpenStack cluster to the latest version
of Mirantis OpenStack. It is possible with Fuel deployment framework.

We must prepare a host in the source cloud for rolling upgrade to Mirantis
OpenStack. Preparations include removing all virtual resources from that host
and disabling of provisioning new resources to it.

Removing resources combines 2 processes:

* moving targeted workloads to the Mirantis OpenStack cluster with Pumphouse
application;
* moving remaining workloads to other hosts in source cloud with live/block
migration or evacuate/rebuild.

Both are implemented in `scripts/migration.py` script. Move designated resources
to Mirantis OpenStack with `migrate` subcommand. Move remaining resources within
Source cloud with `evacuate` subcommand. See details in
[`scripts/README.md`](../scripts/README.md) file.

## Upgrade host

Use `nova hypervisor-list`, `nova hypervisor-show` commands to identify which
hosts are cleansed from all work load. To decomission host from the existing
cloud and move it to Mirantis OpenStack, use script `scripts/migrate_host.py`.
See usage details for that script in 
[`scripts/README.md`](../scripts/README.md) document.

To perform the upgrade, you have to connect the host to Fuel-managed PXE network,
reboot it into PXE bootstrap, configure it in the Fuel API and start deployment.

Following steps are performed by the upgrade script:

- configure host to boot from PXE boot server using IPMI
- reset host via IPMI Power Control function
- wait for host to boot into bootstrap image via PXE and self-register as node
  in Fuel deployment framework
- assign 'compute' role to the node via Fuel API
- start deployment of host as in Mirantis OpenStack cluster via Fuel API

After deployment has started, you could check it's progress in Fuel UI or via
Fuel CLI client.

### Decomission source cloud

If the ultimate goal of the migration process is to completely replace existing
OpenStack infrastructure with Mirantis OpenStack, then as a final step of the
move controllers of the source cloud should be decomissioned and added to
Mirantis OpenStack cluster.

Steps for decomissioning the controller node are generally the same as steps to
move compute node from source to destination cluster and could be automatically
done with the same script.
