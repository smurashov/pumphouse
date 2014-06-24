# Pumphouse scripts

This directory contains scripts that implement main tasks of the Pumphouse
utility.

## `migration.py` - Simple migration script

This script migrates servers from one instance of Devstack to another Devstack
using APIs of OpenStack services. You could look up a list of resources affected
by this script using the following command:

```sh
$ python scripts/migration.py -h
```

To migrate resources from one cloud to another, add configuration of endpoints
of source and destination clouds to configuration file `config.yaml`. See
example in `devstack/config.yaml` file.

Now prepare your source cloud for the test run by adding certain resources to
it. Use `setup` flag of the migration script:

```sh
$ python scripts/migration.py config.yaml setup
```

Then run migration script as follows:

```sh
$ pyhon scripts/migration.py config.yaml migrate
```

If you need to clean your target cloud up, run migration script with `cleanup`
command:

```sh
$ python scripts/migration.py config.yaml cleanup
```

## `migrate_host.py` - Host upgrade to Mirantis OpenStack

This script upgrades a hypervisor node from the source cloud to Mirantis
OpenStack Compute node and attaches it to the target MOS cluster.

Script command format is as follows:
```sh
$ python scripts/migrate_host.py [-h] [-i INVENTORY] [-e ENV_ID] hostname
```

`INVENTORY` is a YaML formatted file with the inventory of hardware present in
the environment and some additional configuration information. See `samples/`
for the example of inventory file. Defaults to `./inventory.yaml`.
`ENV_ID` is an identifier number of the target Mirantis OpenStack cluster in
Fuel. Defaults to `1`.
`hostname` is a reference to host configuration in `'hosts'` section of the
inventory YaML.
