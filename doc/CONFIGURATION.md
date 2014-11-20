# Pumphouse Configuration File

All Pumphouse binaries and scripts require that path to the configuration file
is specified as a first argument. Configuration file is a YAML file. It has
following sections:

* `CLOUDS` section contains parameters of `source` and `destination` clouds in
  corresponding subsections.
* `PLUGINS` section contains names of plugins and implementation that should be
  used.
* `CLOUD_RESET` parameter is Boolean and it defines if Pumphouse service should
  handle `/reset` API call. This function is intended for test/demo environments
  only and should not be enabled in real installations. Defaults to `False`.
* `SERVER_NAME` parameter tells `pumphouse-api` where it should listen to
  Pumphouse API calls. Contains IP address and port number. Port number, if
  omitted, defaults to 5000.
* `DEBUG` is a Boolean parameter to turn debugging on/off for `pumphouse-api`
  binary.

## `CLOUDS` Configuration

This section contains 2 subsections: `source` and `destination` for
corresponding clouds. Both sections must contain following parameters:

* `endpoint` is a list of credentials to authenticate with OpenStack cloud:
  * `auth_url` is URL of Keystone service
  * `username` is name of administor, usually 'admin'
  * `password` is admin's password
  * `tenant_name` is a default tenant for admin user, usually 'admin'
* `identity` configures DB endpoint used to handle password hashes:
  * `connection` contains connection string in an `sqlalchemy` format
* `populate` contains a list of parameters used by test `setup` function for
  auto-populating `source` cloud with testing resources. Doesn't do anything
  when added to configuration of `destination` cloud.
* `urls` is a list of links to cloud's dashboards:
  * `horizon` is a link to OpenStack Dashboard
  * `mos` is a link to Fuel dashboard (only for `destination` cloud config)
