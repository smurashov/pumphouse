## Resources

Pumphouse migrates certain cloud resources managed by corresponding services of
OpenStack.

Service | List of resources
--- | ---
Nova | - instances
     | - keypairs
     | - security groups
     | - quotas
     | - flavors
     | - networks (fixed + floating ips)
Glance | - image files
Keystone | - tenants
         | - users
         | - roles
         | - user-roles assignments

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

#### Quotas

##### Dependencies

- tenants
- users

##### Migration strategy

##### Migration path

#### Security groups

##### Dependencies

Security groups themseleves don't depend on any resources.

##### Migration strategy

##### Migration path

#### Networks

##### Migration strategy

##### Migration path

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

##### Migration path

