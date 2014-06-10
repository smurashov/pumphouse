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
