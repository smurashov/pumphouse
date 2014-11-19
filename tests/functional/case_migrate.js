var TestCase = require('./test_case');
var Config = require('./config');
var Cloud = require('./cloud');

var MigrateTestCase = new TestCase('Tenant migration');

MigrateTestCase.addStep('Calling API to fetch resources', function() {
    this.test_case.api.resources(function(err, res) {
        if (err) this.fail('Resources fetching error');

        this.test_case.context.state = new Cloud(res.body);
        return this.next();
    }.bind(this))
});

MigrateTestCase.addStep('Looking for preconfigured tenant in source cloud', function() {
    var context = this.test_case.context,
        b = context.state;

    console.log('Got cloud resources', b.toString());

    // Looking for predefined tenant in the source cloud
    var t = b.get(Config.tenant);
    if (t) {
        context.tenant = t;
        return this.next();
    }
    this.fail('Unable to find tenant "' + Config.tenant.id + '" in source cloud');
});

MigrateTestCase.addStep('Initiate tenant migration', function() {
    var tenant = this.test_case.context.tenant;

    this.test_case.api.migrateTenant(tenant.id, function(err, res) {
        if (err) this.fail('Tenant (' + tenant.id + ') migration initialization failed');

        return this.next();
    }.bind(this))
});

MigrateTestCase.addStep('Listening for tenant migration start event', function() {
    var tenant = this.test_case.context.tenant;

    this.test_case.events
        .on('update')
        .of(Config.tenant)
        .execute(
            function(m) {
                if (m.action == 'migration') {
                    console.log('Tenant ' + tenant.id + ' migration started');
                    return this.next();
                }
                return false;
            }.bind(this))
});

MigrateTestCase.addStep('Listening for tenant migration finish event', function() {
    var tenant = this.test_case.context.tenant;

    this.test_case.events
        .on('update')
        .of(Config.tenant)
        .execute(
            function(m) {
                if (m.action == '') {
                    console.log('Tenant ' + tenant.id + ' migration completed');
                    return this.next();
                }
                return false;
            }.bind(this)
        )
});

MigrateTestCase.addStep('Saving previous cloud configuration', function() {
    var context = this.test_case.context;

    context.initial_state = context.state;
    return this.next();
});

MigrateTestCase.repeatStep(0);

MigrateTestCase.addStep('Looking for preconfigured tenant in destination cloud', function() {
    var context = this.test_case.context,
        tenant = context.tenant,
        b = context.state;

    console.log('Got clouds resources', b.toString());

    // Looking for predefined tenant in the destination cloud
    var t = b.getAll({
        'type': 'tenant',
        'cloud': 'destination',
        'data.name': tenant.data.name
    });
    if (t.length) {
        context.new_tenant = t[0];
        return this.next();
    }
    this.fail('Unable to find tenant "' + tenant.data.name + '" in destination cloud');
});

MigrateTestCase.getTenantServers = function(tenant_id, resources, cloud) {
    var servers = {},
        tenant_servers = resources.getAll({
            'type': 'server',
            'cloud': cloud,
            'data.tenant_id': tenant_id
        }),
        images = {},
        cloud_images = resources.getAll({
            'type': 'image',
            'cloud': cloud
        }),
        floating_ips = {},
        cloud_floating_ips = resources.getAll({
            'type': 'floating_ip',
            'cloud': cloud
        });

    for (var i in cloud_images)
        images[cloud_images[i].id] = cloud_images[i].data.name;

    for (var i in cloud_floating_ips) {
        var ip = cloud_floating_ips[i];
        if (!floating_ips[ip.data.server_id]) floating_ips[ip.data.server_id] = [];
        floating_ips[ip.data.server_id].push(ip.data.name);
    }

    for (var i in tenant_servers) {
        var s = tenant_servers[i];
        console.log(JSON.stringify(s));

        // Assigning image
        s.image_name = s.data.image_id ? images[s.data.image_id]: '';

        // Assigning all floating ips
        s.floating_ips = floating_ips[s.id] ? floating_ips[s.id].sort().join(',') : '';

        servers[s.name] = s;
    }
    return servers;
};

MigrateTestCase.makeServerPrintable = function(s) {
    return JSON.stringify({
        'id': s.id,
        'name': s.data.name,
        'image_name': s.image_name,
        'floating_ips': s.floating_ips
    });
};

MigrateTestCase.assureServersEqual = function(s1, s2) {
    for (var i in s1) {
        var s = s1[i], so = s2[i];

        if (!so) this.fail('Unable to find server "' + s.name + '"');

        if (s.image_name != so.image_name) this.fail('Server "' + s.name + '" uses different image ("' + s.image_name + '" vs "' + so.image_name + '")');

        if (s.floating_ips != so.floating_ips) this.fail('Server "' + s.name + '" has different set of floating ips ("' + s.floating_ips + '" vs "' + so.floating_ips + '")');

        console.log(' - ' + this.makeServerPrintable(s) + ' = ' + this.makeServerPrintable(so))
    }
};

MigrateTestCase.addStep('Making sure tenants are equal', function() {
    var context = this.test_case.context,
        old = context.tenant,
        now = context.new_tenant,
        src = context.initial_state,
        dst = context.state;

    // Making sure tenants are equal
    if (old.description != now.description) this.fail('Tenants descriptions differ');

    // Checking that all entities that relate to these tenants are the same
    var src_servers = this.test_case.getTenantServers(old.id, src, 'source');
    var dst_servers = this.test_case.getTenantServers(now.id, dst, 'destination');

    console.log('Assure source tenant servers are the same with destination ones');
    this.test_case.assureServersEqual(src_servers, dst_servers);

    console.log('Assure destination tenant servers are the same with source ones');
    this.test_case.assureServersEqual(dst_servers, src_servers);

    this.next();

});

exports.testcase = MigrateTestCase;
