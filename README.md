Pumphouse
=========

The goal of this project is to provide a tool for migrating workloads (i.e.
tenants and their resources) from arbitrary OpenStack cloud to Mirantis
OpenStack cloud. Source cloud must comply to certain limitations (see below).
Miranits OpenStack cloud should be installed next to existing cloud, using Fuel
automated deployment framework.

## Requirements and constraints

- Source OpenStack releases supported:
  - Grizzly (2013.1)
  - Havana (2013.2)
  - Icehouse (2014.1)
- Source OpenStack has `nova-network` for networking manager
- Network schema is FlatDHCP
- Only stateless workloads shall be migrated
- Migrated instances only have ephemeral storage
- Every node must have at least 2 NICs:
  - Admin/PXE boot network
  - Management/Public/Private networks
