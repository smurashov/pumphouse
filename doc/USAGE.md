Usage Scenario
==============

Pumphouse application is intended to be used by cloud operators or service
engineers to perform forklift upgrade of OpenStack-based cloud. This type of
upgrade assumes that the new OpenStack installation works on the same set of
hardware as original cloud. Workloads and resources are moved one by one from
the original cloud to upgrade target cloud. Every physical hypervisor node of
the existing cloud eventually gets added to upgraded cluster and re-installed as
it`s Compute node.

Pumphouse assumes that upgrade target cloud is managed by Fuel deployment
engine. For original cloud, both Fuel API and IPMI management modes are
supported.

## Install pumphouse

Pumphouse is a python application and can be installed as a pip package:

```ShellSession
$ pip install pumphouse
```

## Acquire initial nodes

Optionally, Pumphouse might allow to prepare nodes for deployment of initial
Upgrade Target cloud. This preparation includes following steps:

- install `pumphouse` package onto a node that has access to following networks:
  *public/management API network* of Source cloud; *IPMI management network* of
  Source cloud.
- use Pumphouse to move virtual instances from certain nodes in existing cloud
  (via evacuate or live migrate or rebuild)
- move released bare metal nodes to isolated L2 network (VLAN) which will serve
  as Admin network for Fuel deployment framework

## Install Upgrade Target cloud

Currently, Pumphouse does not handle installation of 'seed' for Upgrade Target
cloud. It is operator's responsibility to properly configure environment and
initial set of Compute nodes via Fuel UI or API. Pumphouse will use the
configuration of initail Compute nodes as a template to add upgraded hypervisors
to target environment.

## Configure source and target clouds in Pumphouse

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

Pumphouse provides Web service with HTTP-based API. See API specification in the
[document](API.md).

CLI script included with Pumphouse allows for granular migration of resources,
including individual images, all servers of a project or all identity resources
(tenants, users, roles, etc).

## Maintenance mode on hosts

Pumphouse leverages Fuel deployment framework for upgrade of hypervisor hosts.
Preparations for upgrade include removing all virtual resources from that host
and disabling of provisioning new resources to it. This is also called
*maintenance mode* of host.

Maintenance mode requires 2 steps:

* moving targeted workloads to the Upgrade Target cluster with Pumphouse
application;
* moving remaining workloads to other hosts in source cloud with live/block
migration or evacuate/rebuild.

## Upgrade host

To perform the upgrade, you have to connect the host to Fuel-managed PXE network,
reboot it into PXE bootstrap, configure it in the Fuel API and start deployment.

Following steps are performed by Pumphouse during upgrade procedure:

- configure host to boot from PXE boot server using IPMI
- reset host via IPMI Power Control function
- wait for host to boot into bootstrap image via PXE and self-register as node
  in Fuel deployment framework
- assign 'compute' role to the node via Fuel API
- configure disk drives and network interfaces consistently with existing
  Compute nodes preconfigured by operator
- start deployment of the host as Compute node OpenStack cluster via Fuel API

After deployment has started, you could check it's progress in Fuel UI or via
Fuel CLI client.

### Decomission source cloud

If the ultimate goal of the migration process is to completely replace original
OpenStack infrastructure with new release, then as a final step of the move
controllers of the source cloud should be decomissioned and added to Mirantis
OpenStack cluster.
