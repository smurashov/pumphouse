# Pumphouse scripts

To use scripts install pumphouse package. The package contains scripts that
implement main tasks of the Pumphouse utility.

To perform installation with a third-party user interface the package should be
prepared. It is a simple action and it require just copy files in the
pumphouse/api/static directory. A file with the index.html name must be there.

To install the pumphouse package use the command:

```sh
$ pip install --allow-external mysql-connector-python .
```

Two commands would be avaiable in your environment:

* `pumphouse`
* `pumphouse-bm`

## `pumphouse` - Simple migration script

This script migrates servers from one instance of Devstack to another Devstack
using APIs of OpenStack services. You could look up a list of resources affected
by this script using the following command:

```sh
$ pumphouse --help
```

To migrate resources from one cloud to another, add configuration of endpoints
of source and destination clouds to configuration file `config.yaml`. See
example in `devstack/config.yaml` file.

Now prepare your source cloud for the test run by adding certain resources to
it. Use `setup` flag of the migration script:

```sh
$ pumphouse config.yaml setup
```

Then run migration script as follows:

```sh
$ pumphouse config.yaml migrate <resource_class>
```

`<resource_class>` could be one of the following:

* `servers`
* `tenants`
* `users`
* `roles`
* `flavors`
* `images`

If you need to clean your source or target cloud up, run migration script 
with `cleanup` command and specify which cloud you want to clean up:

```sh
$ pumphouse config.yaml cleanup { source | destination }
```

## `pumphouse-bm` - Host upgrade to Mirantis OpenStack

This script upgrades a hypervisor node from the source cloud to Mirantis
OpenStack Compute node and attaches it to the target MOS cluster.

Script command format is as follows:
```sh
$ pumphouse-bm [-h] [-i INVENTORY] [-e ENV_ID] hostname
```

`INVENTORY` is a YaML formatted file with the inventory of hardware present in
the environment and some additional configuration information. See `samples/`
for the example of inventory file. Defaults to `./inventory.yaml`.
`ENV_ID` is an identifier number of the target Mirantis OpenStack cluster in
Fuel. Defaults to `1`.
`hostname` is a reference to host configuration in `'hosts'` section of the
inventory YaML.
