import logging

from keystoneclient.openstack.common.apiclient import exceptions \
    as keystone_excs
from novaclient import exceptions as nova_excs

from pumphouse import cloud
from pumphouse import exceptions
from pumphouse import management
from pumphouse import utils


LOG = logging.getLogger(__name__)


def migrate_role(mapping, events, src, dst, id):
    r0 = src.keystone.roles.get(id)
    if r0.id in mapping:
        LOG.warn("Skipped because mapping: %s", r0._info)
        return r0, dst.keystone.roles.get(mapping[r0.id])
    try:
        r1 = dst.keystone.roles.find(name=r0.name)
    except keystone_excs.NotFound:
        r1 = dst.keystone.roles.create(r0.name)
        LOG.info("Created: %s", r1._info)
    else:
        LOG.warn("Already exists: %s", r1._info)
    mapping[r0.id] = r1.id
    return r0, r1


def update_users_passwords(mapping, events, src, dst):
    def with_mapping(identity):
        for user_id, password in identity.iteritems():
            yield mapping[user_id], password

    dst.identity.update(with_mapping(src.identity))
    dst.identity.push()


def get_user(mapping, events, src, dst, id):
    try:
        return dst.keystone.users.get(id)
    except keystone_excs.NotFound:
        return
    return


def migrate_user(mapping, events, src, dst, id):
    u0 = src.keystone.users.get(id)
    user_dict = dict(name=u0.name,
                     password='default',
                     enabled=u0.enabled)
    if hasattr(u0, "tenantId"):
        _, t1 = migrate_tenant(mapping, events, src, dst, u0.tenantId)
        user_dict['tenant_id'] = t1.id
    if hasattr(u0, "email"):
        user_dict['email'] = u0.email
    try:
        LOG.debug("Looking up user in dst by username: %s", u0.username)
        u1 = dst.keystone.users.find(name=u0.name)
    except keystone_excs.NotFound:
        src.identity.fetch(u0.id)
        u1 = dst.keystone.users.create(**user_dict)
        LOG.info("Created: %s", u1._info)
        LOG.warn("Password for %s doesn't match the original user!", u1.name)
        # TODO(ogelbukh): Add password synchronization logic here
    else:
        LOG.warn("Already exists: %s", u1._info)
    mapping[u0.id] = u1.id
    for tenant in src.keystone.tenants.list():
        _, t1 = migrate_tenant(mapping, events, src, dst, tenant.id)
        user_roles = src.keystone.roles.roles_for_user(u0.id, tenant=tenant.id)
        for user_role in user_roles:
            _, r1 = migrate_role(mapping, events, src, dst, user_role.id)
            try:
                dst.keystone.roles.add_user_role(u1.id, r1.id, t1)
            except keystone_excs.Conflict:
                LOG.warn("Role %s already assigned to user %s in tenant %s",
                         u1.name,
                         r1.name,
                         tenant.name)
            else:
                LOG.info("Created role %s assignment for user %s in tenant %s",
                         u1.name,
                         r1.name,
                         tenant.name)
    return u0, u1


def migrate_tenant(mapping, events, src, dst, id):
    t0 = src.keystone.tenants.get(id)
    if t0.id in mapping:
        LOG.warn("Skipped because mapping: %s", t0._info)
        return t0, dst.keystone.tenants.get(mapping[t0.id])
    try:
        t1 = dst.keystone.tenants.find(name=t0.name)
    except keystone_excs.NotFound:
        t1 = dst.keystone.tenants.create(t0.name,
                                         description=t0.description,
                                         enabled=t0.enabled)
        LOG.info("Created: %s", t1._info)
    else:
        LOG.warn("Already exists: %s", t1._info)
    mapping[t0.id] = t1.id
    return t0, t1


def migrate_image(mapping, events, src, dst, id):
    def upload(src_image, dst_image):
        data = src.glance.images.data(src_image.id)
        dst.glance.images.upload(dst_image.id, data._resp)
        LOG.info("Uploaded image: %s -> %s", src_image, dst_image)

    def create(image, **kwargs):
        new = dst.glance.images.create(disk_format=image.disk_format,
                                       container_format=image.container_format,
                                       visibility=image.visibility,
                                       min_ram=image.min_ram,
                                       min_disk=image.min_disk,
                                       name=image.name,
                                       protected=image.protected,
                                       **kwargs)
        LOG.info("Create image: %s", new)
        return new
    i0 = src.glance.images.get(id)
    if i0.id in mapping:
        LOG.warn("Skipped because mapping: %s", dict(i0))
        return i0, dst.glance.images.get(mapping[i0.id])
    imgs1 = dict([(i.checksum, i)
                  for i in dst.glance.images.list()
                  if hasattr(i, "checksum")])
    if not hasattr(i0, "checksum"):
        LOG.exception("Image has no checksum: %s", i0.id)
        raise exceptions.NotFound("There is no checksum for image {!r}"
                                  .format(i0.id))
    elif i0.checksum not in imgs1:
        params = {}
        if hasattr(i0, "kernel_id"):
            LOG.info("Found kernel image: %s", i0.kernel_id)
            _, ik1 = migrate_image(mapping, events, src, dst, i0.kernel_id)
            params["kernel_id"] = ik1["id"]
        if hasattr(i0, "ramdisk_id"):
            LOG.info("Found ramdisk image: %s", i0.ramdisk_id)
            _, ir0 = migrate_image(mapping, events, src, dst, i0.ramdisk_id)
            params["ramdisk_id"] = ir0["id"]
        i1 = create(i0, **params)
        upload(i0, i1)
    else:
        i1 = imgs1.get(i0.checksum)
        LOG.info("Already present: %s", i1)
    mapping[i0.id] = i1.id
    return i0, i1


def migrate_flavor(mapping, events, src, dst, id):
    f0 = src.nova.flavors.get(id)
    if f0.id in mapping:
        LOG.warn("Skipped because mapping: %s", f0._info)
        return f0, dst.nova.flavors.get(mapping[f0.id])
    try:
        f1 = dst.nova.flavors.get(f0)
    except nova_excs.NotFound:
        f1 = dst.nova.flavors.create(f0.name, f0.ram, f0.vcpus, f0.disk,
                                     flavorid=f0.id,
                                     ephemeral=f0.ephemeral,
                                     swap=f0.swap or 0,
                                     rxtx_factor=f0.rxtx_factor,
                                     is_public=f0.is_public)
        LOG.info("Created: %s", f1._info)
    else:
        LOG.warn("Already exists: %s", f1._info)
        mapping[f0.id] = f1.id
    return f0, f1


def migrate_network(mapping, events, src, dst, name):
    nets0 = dict((n.label, n) for n in src.nova.networks.list())
    n0 = nets0[name]
    if n0.id in mapping:
        LOG.warn("Skipped because mapping: %s", n0._info)
        return n0, dst.nova.networks.get(mapping[n0.id])
    if n0.project_id:
        # XXX(akscram): Restrict of tenant priviliges.
        _, t1 = migrate_tenant(mapping, events, src, dst, n0.project_id)
        tenant_ns = dst.user_ns.restrict(tenant_name=t1.name)
        tenant_dst = dst.restrict(tenant_ns)
        cloud, project_id = tenant_dst, t1.id
    else:
        cloud, project_id = dst, None
    try:
        n1 = cloud.nova.networks.create(label=n0.label,
                                        cidr=n0.cidr,
                                        cidr_v6=n0.cidr_v6,
                                        dns1=n0.dns1,
                                        dns2=n0.dns2,
                                        gateway=n0.gateway,
                                        gateway_v6=n0.gateway_v6,
                                        multi_host=n0.multi_host,
                                        priority=n0.priority,
                                        project_id=project_id,
                                        vlan_start=n0.vlan,
                                        vpn_start=n0.vpn_private_address)
    except nova_excs.Conflict:
        n1 = cloud.nova.networks.findall(project_id=None)[0]
    mapping[n0.id] = n1.id
    return n0, n1


def migrate_secgroup(mapping, events, src, dst, id):
    sg0 = src.nova.security_groups.get(id)
    try:
        sg1 = dst.nova.security_groups.find(name=sg0.name)
    except nova_excs.NotFound:
        sg1 = dst.nova.security_groups.create(sg0.name,
                                              sg0.description)
        LOG.info("Created: %s", sg1._info)
    else:
        LOG.warn("Already exists: %s", sg1._info)
    for rule in sg0.rules:
        migrate_secgroup_rule(mapping, events, src, dst, rule, sg1.id)
    return sg1


def migrate_secgroup_rule(mapping, events, src, dst, src_rule, id):
    r0 = src_rule
    try:
        r1 = dst.nova.security_group_rules.create(
            id, ip_protocol=r0['ip_protocol'], from_port=r0['from_port'],
            to_port=r0['to_port'], cidr=r0['ip_range']['cidr'])
        LOG.info("Created: %s", r1._info)
    except nova_excs.BadRequest:
        LOG.warn("Duplicate rule: %s", r0)
    except nova_excs.NotFound:
        LOG.exception("Rule create attempted for non-existent "
                      "security group: %s", r0)
        raise nova_excs.NotFound


def migrate_floating_ip(mapping, events, src, dst, ip):

    '''Create IP address in floating IP address pool in destination cloud

    Creates IP address if it does not exist. Creates a pool in destination
    cloud as well if it does not exist.

    :param mapping:     dict mapping entity ids in source and target clouds
    :param src:         Cloud object representing source cloud
    :param dst:         Cloud object representing destination cloud
    :param ip:          IP address
    :type ip:           string
    '''

    floating_ip0 = src.nova.floating_ips_bulk.find(address=ip)
    ip_pool0 = src.nova.floating_ip_pools.find(name=floating_ip0.pool)
    try:
        floating_ip1 = dst.nova.floating_ips_bulk.find(address=ip)
    except nova_excs.NotFound:
        dst.nova.floating_ips_bulk.create(floating_ip0.address,
                                          pool=ip_pool0.name)
        try:
            floating_ip1 = dst.nova.floating_ips_bulk.find(address=ip)
        except nova_excs.NotFound:
            LOG.exception("Not added: %s", ip)
            raise exceptions.Error()  # TODO(ogelbukh): emit event here
        else:
            LOG.info("Created: %s", floating_ip1._info)
            pass  # TODO(ogelbukh): emit event here
    else:
        LOG.warn("Already exists, %s", floating_ip1._info)
        pass  # TODO(ogelbukh): emit event here
    return floating_ip1


def migrate_server(mapping, events, src, dst, id):
    """Migrates the server."""
    def _associate_floating_ip((cloud, floating_ip, server, fixed_ip)):
        try:
            cloud.nova.servers.add_floating_ip(
                server, floating_ip.ip, fixed_ip)
        except nova_excs.BadRequest:
            return (cloud,
                    floating_ip,
                    server,
                    fixed_ip)
        else:
            return (cloud,
                    cloud.nova.floating_ips.get(floating_ip),
                    server,
                    fixed_ip)

    def _get_floating_ip_server((cloud, floating_ip, server, fixed_ip)):
        return floating_ip.instance_id

    s0 = src.nova.servers.get(id)
    if s0.id in mapping:
        LOG.warn("Skipped because mapping: %s", s0._info)
        return s0, dst.nova.servers.get(mapping[s0.id])
    # XXX(akscram): Restriction of client priviliges.
    _, user = migrate_user(mapping, events, src, dst, s0.user_id)
    tenant = dst.keystone.tenants.get(mapping[s0.tenant_id])
    user_ns = cloud.Namespace(username=user.name,
                              tenant_name=tenant.name,
                              password="default")
    user_dst = dst.restrict(user_ns)
    tenant_ns = src.user_ns.restrict(tenant_name=tenant.name)
    tenant_src = src.restrict(tenant_ns)
    _, f1 = migrate_flavor(mapping, events, src, dst, s0.flavor["id"])
    nics = []
    _, i1 = migrate_image(mapping, events, src, user_dst, s0.image["id"])
    addresses = s0.addresses
    floating_ips = dict()
    for n_label, n_params in addresses.iteritems():
        _, n1 = migrate_network(mapping, events, src, dst, n_label)
        fixed_ip = n_params[0]
        floating_ips[fixed_ip["addr"]] = n_params[1:]
        nics.append({
            "net-id": n1.id,
            "v4-fixed-ip": fixed_ip["addr"],
        })
    LOG.info("Network configuration: %s", nics)
    for secgroup in s0.security_groups:
        sg0 = tenant_src.nova.security_groups.find(name=secgroup['name'])
        sg1 = migrate_secgroup(
            mapping, events, tenant_src, user_dst, sg0.id)
    try:
        src.nova.servers.suspend(s0)
        utils.wait_for(s0, src.nova.servers.get, value="SUSPENDED")
        events.emit("server suspended", {"id": s0.id, "cloud": "source"},
                    namespace="/events")
        LOG.info("Suspended: %s", s0._info)
        try:
            s1 = user_dst.nova.servers.create(s0.name, i1, f1, nics=nics)
            s1 = utils.wait_for(s1, dst.nova.servers.get, value="ACTIVE")
            hostname = getattr(s1, "OS-EXT-SRV-ATTR:hypervisor_hostname")
            events.emit("server boot", {
                "cloud": "destination",
                "id": s1.id,
                "name": s1.name,
                "tenant_id": s1.tenant_id,
                "image_id": s1.image["id"],
                "host_name": hostname,
                "status": "boot",
            }, namespace="/events")
        except Exception:
            LOG.exception("Failed to create server: %s", s0._info)
            raise
        else:
            try:
                for fixed_ip, floating_ip_dict in floating_ips.iteritems():
                    floating_ip_range = migrate_floating_ip(
                        mapping, events, src, dst,
                        floating_ip_dict["addr"])
                    floating_ip1 = user_dst.nova.floating_ips.create(
                        pool=floating_ip_range.pool)
                    LOG.info("Created: %s", floating_ip1._info)
                    floating_ip1 = utils.wait_for(
                        (user_dst, floating_ip1, s1, fixed_ip),
                        _associate_floating_ip,
                        attribute_getter=_get_floating_ip_server,
                        value=s1.id,
                        expect_excs=(nova_excs.BadRequest, ))
            except Exception:
                LOG.exception("Failed to assign floating ip: %s",
                              floating_ips[fixed_ip])
                raise
            else:
                src.nova.servers.delete(s0)
                events.emit("server terminate",
                            {"cloud": "source", "id": s0.id},
                            namespace="/events")
                LOG.info("Deleted: %s", s0)
    except Exception:
        LOG.exception("Error occured in migration: %s", s0._info)
        src.nova.servers.resume(s0)
        raise
    mapping[s0.id] = s1.id
    LOG.info("Created: %s", s1._info)
    return s0, s1


def migrate_resources(events, source, destination, tenant_id):
    mapping = {}
    events.emit("tenant migrate", {"id": tenant_id}, namespace="/events")
    src_tenant, dst_tenant = migrate_tenant(mapping, events, source,
                                            destination, tenant_id)
    events.emit("tenant clone", {
        "id": dst_tenant.id,
        "source_id": src_tenant.id,
        "name": dst_tenant.name,
        "description": dst_tenant.description,
        "cloud": "destination",
    }, namespace="/events")
    management.become_admin_in_tenant(destination,
                                      destination.keystone.auth_ref.user_id,
                                      dst_tenant.id)
    for user in src_tenant.list_users():
        migrate_user(mapping, events, source, destination, user.id)
    servers = source.nova.servers.list(search_opts={
        "all_tenants": 1,
        "tenant_id": tenant_id,
    })
    for server in servers:
        # XXX(akscram): Yeah, here is a double check of tenant-servers
        #               association because Nova behaves untrusted.
        if server.tenant_id == tenant_id:
            events.emit("server migrate", {"id": server.id},
                        namespace="/events")
            _, dst_server = migrate_server(mapping, events, source,
                                           destination, server)
            events.emit("server migrated", {
                "source_id": server.id,
                "destination_id": dst_server.id,
            }, namespace="/events")
    update_users_passwords(mapping, events, source, destination)
    events.emit("tenant migrated", {
        "id": tenant_id,
        "new_id": dst_tenant.id,
    }, namespace="/events")
