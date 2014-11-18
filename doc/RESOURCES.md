## Resources

Pumphouse migrates certain cloud resources managed by corresponding services of
OpenStack.

Service | List of resources | Status
--- | ---| ---
Nova | - instances | + |
     | - keypairs | - |
     | - security groups | + |
     | - quotas | - |
     | - flavors | + |
     | - networks (fixed ips) | + |
     | - networks (floating ips) | + |
Glance | - image files | + |
Keystone | - tenants | + |
         | - users | + |
         | - roles | + |
         | - user-roles assignments | + |
Neutron | networks | + |
        | subnets | + |
        | ports | + |
Cinder | volumes | - |

#### Dependencies

There are dependencies between different resources in terms of migration. For
example, to migrate instances from a particular tenant, the corresponding tenant
must be created first in the destination cloud. See below for the list of
dependencies per resource type.

#### Resource categories

On a higher level, all resources could be categorized into two major categories:

* **workload resources** are directly added to workload and explicitly grouped
  by the workload. Servers that execute user processes and volumes that store
  user data are workload resources. See detailed descriptions of workload
  types in [WORKLOADS](WORKLOADS.md) document.
* **meta-resources** provide facilities needed for workload resources. All
  other resources are supplementary, including images, flavors, networks etc.

This distinction makes sense primarily for the user interface of Pumphouse
application. From the standpoint of migration of workloads from one cloud to
another, it is usually doesn't make sense to migrate meta-resources
individually (although we provide this function in our application). Normally,
one chooses from 2 strategies for meta-resources:

* replicate **all** meta-resources from source cloud to target;
* only move resources that migrated workload resources **depend** on.

#### Migration path

General approach to resources migration is that it must be repeatable and
compatible with different achitecture options provided by OpenStack. The most
compatible method to copy **meta-resources** and relocate **workload resources**
is to do it via OpenStack APIs.

Some types of resources require different approach to the migration process.
This section describes the algorithm for every type of resource.

### Glance

#### Images

##### Dependencies

Every image, public or private, is owned by certain tenant. So, images depend on
tenants to be moved to the target cloud.

- tenants
- users (for private images only)

##### Migration path

Images are moved using Glance API calls. It's preferable to transfer images
directly between Glance endpoints, if possible. See `glance-replicator` script
for the reference implementation of this concept.

### Keystone

#### Tenants

##### Dependencies

Tenants don't have dependency on any other resource type to be moved to
destination cloud.

##### Migration path

Tenants are moved via calls to Identity API. Metadata read from source cloud API
and uploaded to destination cloud API.

#### Users

##### Dependencies

For migrating users from source cloud, destination cloud must have the same set
of tenants available. So the list of dependencies is as follows:

- tenants

##### Migration path

Users are moved via calls to Identity API. The only exception to this process
is the Password attribute: it must be copied over directly between state 
databases of source and destination clouds.

#### Roles

##### Dependencies

Role resource does not depend on resources of any other type being defined in
the target cloud.

##### Migration path

Roles are moved via calls to Identity API.

#### User-role assignments

##### Dependencies

User-role assignments depend on the following resources:

- tenants
- users

Note that mapping between resource IDs in source and destination clouds must be
preserved for assignments to be correct.

##### Migration path

User-role assignments are moved via calls to Identity API.

### Nova

#### Flavors

##### Dependencies

Flavors don't depend on any onther resources to be migrated.

##### Migration path

Flavors are read from source cloud and re-created in the destination cloud via
Nova API calls.

#### Keypairs

##### Dependencies

- users

##### Migration path

Retrieval of keypair via API os possible only on per-user basis. Another option
is to migrate keypairs on the database level.

#### Quotas

##### Dependencies

- tenants
- users

##### Migration path

Migration of per-tenant quotas could be performed via Compute API calls.
Default quotas must be set upfront at the time of deployment of the destination
cloud.

#### Security groups

##### Dependencies

Security groups depend on tenants they belong to:

- tenants

##### Migration path

Security groups are read from the source cloud via Compute API.
Security groups are recreated in the destination cloud via Compute API.

#### Networks

##### Dependencies

- tenants

##### Migration path

Moving networks from one cloud to another has a number of implications which
depend on requirements. If it is required that instances can communicate to each
other during the migration process, it is necessary that:

- both clouds use the same network manager
- both clouds share L2 segment(s) used for **private** networks
- `fixed_ip_range` parameters are the same for both clouds
- both clouds share L2 segment(s) for **public** network
- `floating-ip-range` is the same for both clouds

Then migration could be performed via Networking API or using `nova-manage`
command (if network manager is `nova-network`)

#### Instances

##### Dependencies

- tenants
- users
- keypairs
- networks
- security groups
- images
- flavors

##### Migration path

Once all meta-resources for server are copied to target cloud, the path for
virtual server itself is relatively simple:

- **suspend** the instance in source cloud;
- **create** corresponding instance with dependency resoucres in target cloud;
- **verify** that new instance is up and runnning properly, and
- **shutdown** the instance in source cloud.

Note that in this scenario we do not retain any data stored on the ephemeral
storage of the original instance. It is possible to do by snapshotting it after
suspension, and move the snapshot to the target cloud to create the new instance
off that snapshot. However, this approach will significantly affect the
performance of migration, while being not necessary for stateless workloads.
