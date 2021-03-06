/*jslint node:true*/

'use strict';

var TestCase = require('./test_case');
var Config = require('./config');
var Cloud = require('./cloud');

var MigrateTestCase = new TestCase('Tenant migration');

MigrateTestCase.addStep('Call /resources API to fetch resources', function () {
    this.test_case.api.resources(function (err, res) {
        if (err) {
            this.fail('Resources fetching error');
        }

        this.test_case.context.state = new Cloud(res.body);
        return this.next();
    }.bind(this));
});

MigrateTestCase.addStep(
    'Look for tenant matched to "' + Config.tenant_name_mask + '" in source cloud',
    function () {
        var context = this.test_case.context,
            res = context.state.resources,
            b = context.state,
            tenant,
            i,
            j;

        console.log('Got clouds resources', b.toString());

        // Looking for the tenant
        for (i in res) {
            if (res.hasOwnProperty(i)) {
                j = res[i];
                if (j.type === 'tenant' &&
                        j.cloud === 'source' &&
                        j.data.name.indexOf(Config.tenant_name_mask) === 0) {
                    tenant = j;
                }
            }
        }

        // Looking for predefined tenant in the source cloud
        if (tenant) {
            context.tenant = tenant;
            console.log('Tenant ' + JSON.stringify(tenant) + ' is matching the mask');
            return this.next();
        }
        this.fail('Unable to find tenant by mask "' + Config.tenant_name_mask + '" in source cloud');
    }
);

MigrateTestCase.addStep('Initiate tenant migration', function () {
    var tenant = this.test_case.context.tenant;

    this.test_case.api.migrateTenant(tenant.id, function (err, res) {
        if (err) {
            this.fail('Tenant (' + tenant.id + ') migration initialization failed');
        }
        this.next();
    }.bind(this));

});


MigrateTestCase.addStep('Handle tenant migration start event', function () {
    var tenant = this.test_case.context.tenant;

    this.test_case.events
        .listenFor('update')
        .of({
            'id': tenant.id,
            'type': 'tenant',
            'cloud': 'source',
            'action': 'migration'
        })
        .execute(function (m) {
            console.log('Tenant ' + tenant.id + ' migration started');
            return this.next();
        }.bind(this));

    this.test_case.events.startListening();
});

MigrateTestCase.addStep('Handle tenant migration finish event', function () {
    var tenant = this.test_case.context.tenant;

    this.test_case.events
        .listenFor('update')
        .of({
            'id': tenant.id,
            'type': 'tenant',
            'cloud': 'source',
            'action': null
        })
        .execute(
            function (m) {
                console.log('Tenant ' + tenant.id + ' migration completed');
                return this.next();
            }.bind(this)
        );

    this.test_case.events.startListening();
});


MigrateTestCase.addStep('Save previous cloud configuration', function () {
    var context = this.test_case.context;

    context.initial_state = context.state;
    return this.next();
});

MigrateTestCase.repeatStep(0);

MigrateTestCase.addStep('Look for preconfigured tenant in destination cloud', function () {
    var context = this.test_case.context,
        tenant = context.tenant,
        b = context.state,
        t = b.getAll({
            'type': 'tenant',
            'cloud': 'destination',
            'data.name': tenant.data.name
        });

    console.log('Got clouds resources', b.toString());

    // Looking for predefined tenant in the destination cloud
    if (t.length) {
        context.new_tenant = t[0];
        return this.next();
    }
    this.fail('Unable to find tenant "' + tenant.data.name + '" in destination cloud');
});

MigrateTestCase.getTenantServers = function (tenant_id, resources, cloud) {
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
        }),
        i,
        ip,
        s;

    for (i in cloud_images) {
        if (cloud_images.hasOwnProperty(i)) {
            images[cloud_images[i].id] = cloud_images[i].data.name;
        }
    }

    for (i in cloud_floating_ips) {
        if (cloud_floating_ips.hasOwnProperty(i)) {
            ip = cloud_floating_ips[i];
            if (!floating_ips[ip.data.server_id]) {
                floating_ips[ip.data.server_id] = [];
            }
            floating_ips[ip.data.server_id].push(ip.data.name);
        }
    }

    for (i in tenant_servers) {
        if (tenant_servers.hasOwnProperty(i)) {
            s = tenant_servers[i];
            console.log(JSON.stringify(s));

            // Assigning image
            s.image_name = s.data.image_id ? images[s.data.image_id] : '';

            // Assigning all floating ips
            s.floating_ips = floating_ips[s.id] ? floating_ips[s.id].sort().join(',') : '';

            servers[s.data.name] = s;
        }
    }
    return servers;
};

MigrateTestCase.makeServerPrintable = function (s) {
    return JSON.stringify({
        'id': s.id,
        'name': s.data.name,
        'image_name': s.image_name,
        'floating_ips': s.floating_ips
    });
};

MigrateTestCase.assureServersEqual = function (s1, s2) {
    var i, s, so;
    for (i in s1) {
        if (s1.hasOwnProperty(i)) {
            s = s1[i];
            so = s2[i];

            if (!so) {
                this.fail('Unable to find server "' + s.data.name + '"');
            }

            if (s.image_name !== so.image_name) {
                this.fail('Server "' + s.data.name + '" uses different image ("' + s.image_name + '" vs "' + so.image_name + '")');
            }

            if (s.floating_ips !== so.floating_ips) {
                this.fail('Server "' + s.data.name + '" has different set of floating ips ("' + s.floating_ips + '" vs "' + so.floating_ips + '")');
            }

            console.log(' - ' + this.makeServerPrintable(s) + ' = ' + this.makeServerPrintable(so));
        }
    }
};

MigrateTestCase.addStep('Make sure tenants are equal', function () {
    var context = this.test_case.context,
        old = context.tenant,
        now = context.new_tenant,
        src = context.initial_state,
        dst = context.state,
        src_servers = this.test_case.getTenantServers(old.id, src, 'source'),
        dst_servers = this.test_case.getTenantServers(now.id, dst, 'destination');

    // Making sure tenants are equal
    if (old.description !== now.description) {
        this.fail('Tenants descriptions differ');
    }

    // Checking that all entities that relate to these tenants are the same
    console.log('Source servers: ', JSON.stringify(src_servers));
    console.log('Destination servers: ', JSON.stringify(dst_servers));

    console.log('Assure source tenant servers are the same with destination ones');
    this.test_case.assureServersEqual(src_servers, dst_servers);

    console.log('Assure destination tenant servers are the same with source ones');
    this.test_case.assureServersEqual(dst_servers, src_servers);

    this.next();

});

exports.testcase = MigrateTestCase;
