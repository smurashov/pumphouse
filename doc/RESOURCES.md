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
Neutron | networks | - |
        | subnets | - |
        | ports | - |

#### Dependencies

There are dependencies between different resources in terms of migration. For
example, to migrate instances from a particular tenant, the corresponding tenant
must be created first in the destination cloud. See below for the list of
dependencies per resource type.

#### Migration strategy

There could be different migration strategies for different types of resources.
For example, it could be reasonable to migrate all tenants from the source
cloud, or only tenants that have resources. Instances could be migrated on
per-tenant, per-host or per-application basis, or any others. See below for the
list of currently supported strategies.

On the low level, Pumphouse provides following strategies:

- **all** moves all resources of this type to the target cloud, if it is allowed
  by the target capacity. Implementation of this strategy should support
  in-advance verification of target capacity and warn the user if it is
  insufficient for the full migration.
- **tenant** strategy is needed to limit the area of effect of potential
  downtime due to migration. It migrates all resources that belong to specified
  tenant. Technically it means that the list of resources in source cloud must
  be filtered by tenant prior to the migration.
- **specific** resources startegy is underlying for all other strategies: it
  allows for migration of explicitly listed resources (usually specified by
  their respective IDs).
- **public** strategy allows to filter resources that could be shared among
  tenants from resources that are only visible to the owner tenant (usually
  images and flavors)
- **used** strategy filters resources that are somehow used to create dependent
  resoucres. For example, image is used if there is a running instance or
  multiple instances based on it, etc.
- **host** strategy filters resources that are associated with particular
  hypervisor hosts (usually virtual servers).

#### Resource categories

On a higher level, all resources could be categorized into two major categories:

* **workload resources** are directly added to workload and explicitly grouped
  by the workload. Servers that execute user processes and volumes that store
  user data are workload resources.
* **supplementary resources** provide facilities needed for workload resources. All
  other resources are supplementary, including images, flavors, networks etc.

This distinction makes sense primarily for the user interface of Pumphouse
application. From the standpoint of migration of workloads from one cloud to
another, it is usually doesn't make sense to migrate supplementary resources
individually (although we provide this function in our application). Normally,
one chooses from 2 strategies for supplementary resources:

* replicate **all** supplementary resources from source cloud to target;
* only move resources that migrated workload resources **depend** on.

#### Migration path

Different types of resources require different approach to the migration
process. This section describes the algorithm for every type of resource.

### Glance

#### Images

##### Dependencies

Every image, public or private, is owned by certain tenant. So, images depend on
tenants to be moved to the target cloud.

- tenants

##### Migration strategy

Images could be migrated by one of the following strategies:

- *all* moves all images existing in the source cloud in a single batch,
  requires all tenants be migrated in advance
- *public* moves only public images, leaving private images intact
- *tenant* moves only images owned by the particular tenant
- *specific* moves an image(s) specified by ID

##### Migration path

Images are moved using Glance API calls. It's preferable to transfer images
directly between Glance endpoints, if possible. See `glance-replicator` script
for the reference implementation of this concept.

### Keystone

#### Tenants

##### Dependencies

Tenants don't have dependency on any other resource type to be moved to
destination cloud.

##### Migration strategy

Three strategies allowed for migrating tenants:

- *all* to move all tenants created in source cloud in a single batch
- *used* to move only those tenants that have resources belonging to them (i.e.
  users, instances or images)
- *specific* to move only tenant(s) specified by name or ID

##### Migration path

Tenants are moved via calls to Identity API. Metadata read from source cloud API
and uploaded to destination cloud API.

#### Users

##### Dependencies

For migrating users from source cloud, destination cloud must have the same set
of tenants available. So the list of dependencies is as follows:

- tenants

##### Migration strategy

Following strategies are supported for migrating users:

- *all* moves all users from all tenants available in the source cloud, given 
  the dependencies are satisfied
- *tenant* moves all users from the given tenant in the source cloud
- *specific* moves users specified by name or ID

##### Migration path

Users are moved via calls to Identity API. The only exception to this process
is the Password attribute: it must be copied over directly between state 
databases of source and destination clouds.

#### Roles

##### Dependencies

Role resource does not depend on resources of any other type being defined in
the target cloud.

##### Migration strategy

Following strategies are supported for migrating roles:

- *all* moves all role definitions from source to destination cloud

##### Migration path

Roles are moved via calls to Identity API.

#### User-role assignments

##### Dependencies

User-role assignments depend on the following resources:

- tenants
- users

Note that mapping between resource IDs in source and destination clouds must be
preserved for assignments to be correct.

##### Migration strategy

Assignments could be migrated by one of the following strategies:

- *all* recreates all assignments that exist in the source cloud, given all
  users and roles are already recreated in the target cloud
- *tenant* migrates role assignments for the specified tenant
- *specified* strategy migrates only assignments explicitly specified by
  operator

##### Migration path

User-role assignments are moved via calls to Identity API.

### Nova

#### Flavors

##### Dependencies

Flavors don't depend on any onther resources to be migrated.

##### Migration strategy

There is a single strategy for migrating flavors: *all*.

##### Migration path

Flavors are read from source cloud and re-created in the destination cloud via
Nova API calls.

#### Keypairs

##### Dependencies

- users

##### Migration strategy

Following startegies are possible to migrate keypairs:

- *all*
- *user* to move all keypairs owned by the specified user
- *specific* moves only keypair(s) specified by name(s) or fingerprint(s)

##### Migration path

Retrieval of keypair via API os possible only on per-user basis. Another option
is to migrate keypairs on the database level.

#### Quotas

##### Dependencies

- tenants
- users

##### Migration strategy

Per-tenant quotas could be migrated via 2 strategies:

- *all*
- *tenant*

Default quotas cannot be updated via API and must be configured at the
configuration stage of deloyment of Mirantis OpenStack cloud.

##### Migration path

Migration of per-tenant quotas could be performed via Compute API calls.
Default quotas must be set upfront at the time of deployment of the destination
cloud.

#### Security groups

##### Dependencies

Security groups depend on tenants they belong to:

- tenants

##### Migration strategy

Following strategies could be used to migrate security groups:

- *all*
- *specific*

##### Migration path

Security groups are read from the source cloud via Compute API.
Security groups are recreated in the destination cloud via Compute API.

#### Networks

##### Dependencies

- tenants

##### Migration strategy

Following strategies supported for migrating networks:

- *all*
- *tenant*

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

##### Migration strategy

For our use case we should support the following strategies of migration of
virtual server instances:

- *tenant* moves all (or portion of all) virtual servers that belong to the
  given tenant to the target cloud.
- *host* moves all virtual servers from the given host to the target cloud
- *specific* moves only listed servers from the source to the target cloud.

Combination of *tenant* and *host* strategies should also be possible to allow
for the following goals:

- only move a single tenant at the moment to reduce the effect of
  maintenance window;
- don't exhaust capacity of the target cloud, but gradually move nodes to
  it as more virtual resources are  relocated.

##### Migration path

Migration path for virtual servers in our case is relatively simple:

- **suspend** the instance in source cloud;
- **create** corresponding instance with dependency resoucres in target cloud;
- **verify** that new instance is up and runnning properly, and
- **shutdown** the instance in source cloud.

Note that in this scenario we do not retain any data stored on the ephemeral
storage of the original instance. It is possible to do by snapshotting it after
suspension, and move the snapshot to the target cloud to create the new instance
off that snapshot. However, this approach will significantly affect the
performance of migration, while being not necessary for stateless workloads.
