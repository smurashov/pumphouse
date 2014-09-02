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
- Every physical node must have at least 2 NICs:
  - Admin/PXE boot network
  - Management/Public/Private networks

Usage
=====

Pumphouse package includes server binary that provides REST HTTP-based API, and
two scripts that can work standalone. Scripts allow for more granularity than
API. Scripts could be used to implement more sophisticated migration strategies.

## Installation

To install the pumphouse package use the command:

```sh
$ pip install --allow-external mysql-connector-python .
```

Alternatively, if you want to install in Python virtual environment, you could
use `tox` with `apitest` env:

```sh
$ tox -e apitest
```

## `pumphouse-api` - Pumphouse API Server

This script provides API server for Pumphouse with UI. To run the server use
the following command:

```sh
$ pumphouse-api [config]
```

The config file is an YAML file with the following structure:

```
DEBUG: true
CLOUDS:
    source: # a role name of the cloud, source or destination
        endpoint: # OpenStack APIs admin access credentials
            auth_url: http://172.18.18.157:5000/v2.0 # URL of the Keystone service
            username: admin # name of the user with administrative access
            password: secrete # password
            tenant_name: admin # name of the administrative tenant
        identity: # Identity store access credentials, for passwords retrieval
            connection: mysql+mysqlconnector://root:stackdb@172.18.18.157/keystone
    destination:
        endpoint:
            auth_url: http://172.18.18.132:5000/v2.0
            username: admin
            password: secrete
            tenant_name: admin
        identity:
            connection: mysql+mysqlconnector://keystone:secrete@172.18.18.132/keystone
```

See example in [`doc/samples/api-config.yaml`](doc/samples/api-config.yaml)
file.

## CLI Scripts

### `pumphouse` - granular migration script

This script migrates resources from one instance of OpenStack to another using
APIs of OpenStack services. You could look up a list of resources supported by
this script using the following command:

```sh
$ pumphouse --help
```

To migrate resources from one cloud to another, add configuration of endpoints
of source and destination clouds to configuration file `config.yaml`. See
example in [`doc/samples/config.yaml`](doc/samples/config.yaml) file.

Note that the format of configuration file for the script differs from one for
the API service.

### `pumphouse-bm` - Host upgrade to Mirantis OpenStack

This script upgrades a hypervisor host from the source cloud to Mirantis
OpenStack Compute node and attaches it to the target MOS cluster.

Script command format is as follows:
```sh
$ pumphouse-bm [-h] [-i INVENTORY] [-e ENV] hostname
```

`INVENTORY` is a YaML formatted file with the inventory of hardware present in
the environment and some additional configuration information. See `samples/`
for the example of inventory file. Defaults to `./inventory.yaml`.
`ENV` is an identifier number of the target Mirantis OpenStack cluster in
Fuel. Defaults to `1`.
`hostname` is a reference to host configuration in `'hosts'` section of the
inventory YaML.

## Quick Start

To quickly try out the Pumphouse, install 2 OpenStack clouds using your
favorite installer. Then install Pumphouse using instructions above, and create
configuration based on samples.

Now prepare your source cloud for the test run by adding certain resources to
it. Use `setup` flag of the migration script:

```sh
$ pumphouse config.yaml setup
```

Then run migration script as follows:

```sh
$ pumphouse config.yaml migrate <resource_class> --ids <ID> [<ID> ...]
```

`<resource_class>` could be one of the following:

* `servers` - migrate servers to admin tenant in destination cloud
* `tenants` - replicate tenants from source cloud in destination cloud
* `users` - copy users from source cloud to destination cloud
* `roles` - replicate roles by names from source cloud to desintation
* `flavors` - copy flavors from source to desintation cloud
* `images` - replicate images from source to destination cloud
* `identity` - replicate complete identity structure (including projects, users
  and roles with assignment) of the source cloud in the destination cloud
* `resources` - migrate all resources that belong to the tenant/project
  identified by its ID in source cloud to the destination cloud

You can obtain <ID>s of resources you want to migrate by using standard
OpenStack clients or Horizon dashboard UI.

If you need to clean your source or target cloud up, run migration script
with `cleanup` command and specify which cloud you want to clean up:

```sh
$ pumphouse config.yaml cleanup { source | destination }
```

## User Interface

To perform installation with a third-party user interface the package should be
prepared. It is a simple action and it require just copy files in the
pumphouse/api/static directory. A file with the index.html name must be there.

You can prepare for running API service with 3rd-party user interface with:

```sh
$ env SERVER_NAME=$SERVER_NAME \
UI_URL=$UI_URL \
make api
```

Set `$SERVER_NAME` to 'address:port' of the server you're installing on. Defaults
to `127.0.0.1:5000`.
Set `$UI_URL` to the working Git repo URL where user interface is being
developed.
