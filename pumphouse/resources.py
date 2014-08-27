import collections


User = collections.namedtuple("user", ("id"))
Role = collections.namedtuple("role", ("id", "name"))
Tenant = collections.namedtuple("tenant", ("id", "name", "description"))
