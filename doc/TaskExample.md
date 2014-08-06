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


## Definition of tasks, flows and everything else

Go through step-by-step to reinvent a few simple tasks and flows. Every unit of
work should be described as a task. There are some base classes on your choice:

* `pumphouse.tasks.BaseCloudTask` - suitable for tasks either interacts with
source cloud or destination cloud.
* `pumphouse.tasks.BaseCloudTask` - both with source and destination.
* `pumphouse.tasks.BaseRetrieveTask` - inherit from `BaseCloudTask` and
suitable for retrieving a resource.

In common case the task that retrieves a Tenant can be simply described e.g.:

```python
class RetrieveTenant(BaseRetrieveTask):
    def retrieve(self, tenant_id):
        tenant = self.cloud.keystone.tenants.get(tenant_id)
        return tenant
```

Now a Tenant can be retrieved from the source cloud and provides this tenant
by the `"tenant"` named variable:

```python
source = Cloud(...)
retrieve_tenant = RetrieveTenant(source
                                 provides="tenant",
                                 rebind=["tenant-id"])
```

In addition create a task which ensures that a tenant exists or would be
created:

```python
class EnsureTenant(BaseCloudTask):
    def execute(self, tenant_info):
        try:
            tenant = self.cloud.keystone.tenants.find(name=tenant_info["name"])
        except exceptions.keystone_excs.NotFound:
            tenant = self.cloud.keystone.tenants.create(
                tenant_info["name"],
                description=tenant_info["description"],
                enabled=tenant_info["enabled"],
            )
            LOG.info("Created tenant: %s", tenant)
        return tenant.to_dict()
```

Lets instantiate the ensure task and bind the required `tenant_info` argument
to the `"tenant"` value which provided be the previous task.

```python
destination = Cloud(...)
ensure_tenant = EnsureTenant(destination,
                             provides="ensured-tenant",
                             rebind=["tenant"])
```

Ok, now we have two tasks which are connected by scope of provided and required
values. To resolve this relationship we should add tasks into a flow e.g.:

```python
flow = linear_flow.Flow("migrate-tenant")
flow.add(retrieve_tenant, ensure_tenant)
```

When this flow will executed the tenant resource would be migrated from the
source cloud to the destination cloud.

Lets figure out a factory to build this kind of flows (a flow migrates a
tenant) and run it:

```python
def migrate_tenant(src, dst, store):
    flow = linear_flow.Flow("migrate-tenant").add(
        tasks.RetrieveTenant(src,
                             provides="tenant",
                             rebind=["tenant-id"]),
        tasks.EnsureTenant(dst,
                           provides="ensured-tenant",
                           rebind=["tenant"]),
    )
    return (flow, store)

store = {
    "tenant-id": "2b655d29fe914ad28ceb60cd2640a5e1",
}
flow = migrate_tenant(source, destination, store)

taskflow.engines.run(flow, engine_conf="parallel", store=store)
```

## The flow factories

In case when several instances of one task are presented in a flow and depend
on certain values of others tasks the unique names of values are necessary to
avoid mistakes in relationships. Both required and prodivded values should have
distinguished names.

The interface of the factory should be simillar this:

```python
def migrate_tenant(src, dst, store, *args):
    flow = Flow("migrate-tenant-{}".format(tenant_id)).add(
        #either add tasks or flows here
    )
    return (flow, store)
```
