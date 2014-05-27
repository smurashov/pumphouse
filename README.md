pumphouse
=========

The goal of this project is to provide a tool for migrating workloads (i.e.
tenants and their resources) from arbitrary OpenStack cloud to Mirantis
OpenStack cloud. Source cloud must comply to certain limitations (see below).
Miranits OpenStack cloud should be installed next to existing cloud, using Fuel
automated deployment framework.

## Main workflow

### Acquire initial nodes

Optionally, pumphouse might allow to clean up nodes for Fuel deployment in the
existing cloud. This requires following steps:

- install pumphouse package
- use pumphouse to move virtual instances from certain nodes in existing cloud
  (via evacuate or live migrate or rebuild)
- move released bare metal nodes to isolated L2 network (VLAN) which will serve
  as Admin network from the standpoint of Fuel framework


### Install Fuel master node

We install Fuel master node on one of the nodes reserved for Mirantis OpenStack.
MIrantis OpenStack must be configured so it shares Private and Public L2 networks
with the existing OpenStack cluster.

![Pumphouse network diagram][pumphouse-network-diagram.png]
