# Pumphouse scripts

This directory contains scripts that implement main tasks of the Pumphouse
utility.

## `migration.py` - Simple migration script

This script migrates servers from one instance of Devstack to another Devstack
using APIs of OpenStack services. You could look up a list of resources affected
by this script using the following command:

```sh
$ python migration.py -h
```
