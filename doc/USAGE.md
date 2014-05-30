Usage Scenario
==============

Pumphouse application is intended to be used by cloud operators or service
engineers to perform rolling upgrade of existing OpenStack-based cloud to
the Mirantis OpenStack cloud. Rolling upgrade means that the new cloud works on
the same set of hardware as original cloud. Workloads and resources are
gradually moved from the existing cloud to Mirantis OpenStack. Every physical
hypervisor node of the existing cloud eventually gets transferred to Miratnis
OpenStack and re-installed as it`s Compute node.

## Install pumphouse

Pumphouse is a python application and can be installed as a pip package:

```ShellSession
$ pip install pumphouse
```

## Configure source and target clouds

Use configuration file pumphouse.yaml to configure source and target clouds:

```yml
  source:
    -
      name:     good_old_openstack
      auth_url: http://10.0.0.1:5000/v2.0/
      username: admin
      password: admin
      tenant:   admin
      token:    UUID
  target:
    -
      name:     mira-os-1
      auth_url: http://api.endpoint.com:5000/v2.0/
      fuel_url: http://127.0.0.1:8000/api/
      username: admin
      password: admin
```

You could configure multiple source and target clouds.

## Migrate resources

Use standard OpenStack clients (installed as dependencies with `pumphouse`
package) to find and identify resources you`d like to migrate.

Use `pump-*` commands to migrate different resources (we refrain from using
`pump <subcommand>` format as `pump` command already used in
[distcc](https://code.google.com/p/distcc/)):

```ShellSession
$ pump-tenants
$ pump-roles
$ pump-users [tenant]
$ pump-user-roles
$ pump-instances <instance> [instance ...] | <host> | <tenant>
$ pump-networks [tenant]
$ pump-images [tenant]
$ pump-quotas [tenant]
$ pump-flavors
$ pump-keypairs [user]
$ pump-secgroups
```

- `<tenant>` tells the command to migrate only resources that belong to specific 
  tenant. Could be name or ID of the tenant.
- `instance` tells the command to move only specified instance. Could be name or
  ID of the instance
- `host` is a host name or IP address of hypervisor host. All resources from
  that host will be moved to the target cloud

## Migrate hypervisors

Use `nova hypervisor-*` commands to identify which hosts are cleansed from all
workload. To decomission host from the existing cloud and move it to Mirantis
OpenStack, use `pump-host` command:

```ShellSession
$ pump-host <hostname> [hostname ...]
```

As a result, host `<hostname>` will be powered down, rewired to isolated Admin
network and powered up. Then the host will boot via PXE from Fuel node, register
in Fuel as a compute node. Finally, operating systeme and OpenStack services
will be deployed on it.
