# Workload Types

OpenStack manages virtualization infrastructure that provides resources to end
users. Users run their applications on those resources.

Workloads are logical groups of OpenStack resources, used to run single
application or set of interconnected applications and serving a common task.
Certain types of resources directly run applications (virtual servers) or
store user data (block volumes). Other types are meta-resources on which
workload resources depend.

Using workloads as units for migration ensures that impact from upgrade process
to applications of end users will be manageable and as minimal as possible (i.e.
limited to certain maintenance window timeframe).

Pumphouse roadmap includes support for the following types of workloads:

* Single virtual server workload (supported in 0.1)
* Nova project workload (planned in 1.0)
* Heat Stack workload (planned for future)

Following sections give detailed description of those workload types and how
Pumphouse handles them.

### Virtual server workload

The minimal sensible workload is a single virtual server that runs user
applications. Server depends on multiple meta-resources, including flavor,
image, identity etc. Detailed dependencies are listed in
[RESOURCES](RESOURCES.md) document.

### Nova project workload

Nova has a concept of projects. According to [OpenStack
glossary](http://docs.openstack.org/glossary/content/glossary.html), project is
a logical grouping of resources within Compute which defines quotas and access
to VM images. This definition is very similar to the one in Pumphouse.

Project workload includes not just virtual servers and meta-resources they
directly depend on, but also meta-resources that are not currently being used
by active servers though still belong to the project.

### Heat Stack workload

Heat Stack constitutes a set of reousrces orchestrated by Heat to provide a
certain service. Moreover, Stack usually contains explicit list of dependency
meta-resources for the workload. It makes Stack and its migration the next
priority for Pumphouse development.
