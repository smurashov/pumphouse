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

```sh
$ pip install pumphouse
```

## Configure source and target clouds

Use configuration file pumphouse.yaml to configure source and target clouds:

```yml
  sources:
    -
      name:     good_old_openstack
      auth_url: http://10.0.0.1:5000/v2.0/
      username: admin
      password: admin
    -
      name:     grizzly-cloud
      auth_url: https://10.10.10.10:5000/v2.0/
      token:    UUID
  targets:
    -
      name:     mira-os-1
      auth_url: http://api.endpoint.com:5000/v2.0/
      username: admin
      password: admin
```

You could configure multiple source and target clouds.

## Migrate resources

Use standard OpenStack clients (installed as dependencies with `pumphouse`
package) to find and identify resources you`d like to migrate.

Use `pump-` commands to migrate different resources:

```sh
$ pump-tenants
$ pump-roles
$ pump-users [tenant]
$ pump-user-roles
$ pump-instances [tenant [tenant ...] | instance [instance ...]]
$ pump-networks [tenant]
$ pump-images [tenant]
$ pump-quotas [nova | glance]
```
