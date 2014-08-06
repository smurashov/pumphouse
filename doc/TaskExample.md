# Using TaskFlow in Pumphouse

The [TaskFlow](https://wiki.openstack.org/wiki/TaskFlow) is a library which
based on the
[dataflow programming](http://en.wikipedia.org/wiki/Dataflow_programming)
paradigm. In view of this fact the library provides primitives for describing
units of works, their relationships and something more. Pump House uses these
features to represent of migration workflows.


## Clients for clouds

The standard OpenStack clients are collected in the `pumphouse.cloud.Cloud`
class to have only one point for interaction with them e.g:

```python
cloud = Cloud(...)
#list servers, users and images
print(cloud.nova.servers.list())
print(cloud.keystone.users.list())
print(cloud.glance.images.list())
```

At the moment only next clients supported:
[python-novaclient](https://github.com/openstack/python-novaclient),
[python-keystoneclient](https://github.com/openstack/python-keystoneclient) and
[python-glanceclient](https://github.com/openstack/python-glanceclient).


## Definition of a new task

Every operation should be described as a task. There are some base classes on
your choice:

* `pumphouse.tasks.BaseCloudTask` - suitable for tasks either interacts with
source cloud or destination cloud.
* `pumphouse.tasks.BaseCloudTask` - both witch source and destination.
* `pumphouse.tasks.BaseRetrieveTask` - inherit from `BaseCloudTask` and
suitable for retrieving a resource.

In common case the task that retrieves a Tenant can be simply described e.g.:

```python
class RetrieveTenant(BaseRetrieveTask):
    def retrieve(self, tenant_id):
        tenant = self.cloud.keystone.tenants.get(tenant_id)
        return tenant
```

The example of a task which retrieve a Tenant resource identified by the named
variable `tenant-id`:

```python
source = Cloud(...)
retrieve_tenant = RetrieveTenant(source
                                 provides="tenant",
                                 rebind=["tenant-id"])
```
