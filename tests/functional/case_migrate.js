var TestCase = require('./test_case');
var Config = require('./config');

var MigrateTestCase = new TestCase('Tenant migration');

MigrateTestCase.addStep('Calling API to fetch resources', function() {
    this.test_case.api.resources(function(err, res) {
        if (err) this.fail('Resources fetching error');
        this.test_case.context.body = res.body;
        this.next();
    }.bind(this))
});

MigrateTestCase.findTenant = function(cloud) {
    // Looking for predefined tenant in the source cloud
    for (var j = 0, l = cloud.tenants.length; j < l; j++) {
        var t = cloud.tenants[j];
        if (t.name === Config.tenant) {
            console.log('Found tenant: ', t);
            return t;
        }
    }
    return false
};

MigrateTestCase.addStep('Looking for preconfigured tenant in source cloud', function() {
    var context = this.test_case.context, b = context.body;
    console.log('Got the response', b);

    // Looking for predefined tenant in the source cloud
    var t = this.test_case.findTenant(b.source);
    if (t) {
        context.tenant = t;
        context.source_cloud = b.source;
        return this.next();
    }
    this.fail('Unable to find tenant "' + Config.tenant + '" in source cloud');
});

MigrateTestCase.addStep('Initiate tenant migration', function() {
    var tenant = this.test_case.context.tenant;
    this.test_case.api.migrateTenant(tenant.id, function(err, res) {
        if (err) this.fail('Tenant (' + tenant.id + ') migration initialization failed');
        this.next();
    }.bind(this))
});

MigrateTestCase.addStep('Listening for tenant migrated event', function() {
    var tenant = this.test_case.context.tenant;
    this.test_case.events.on('tenant migrated', function(m) {
        if (m.id == tenant.id) {
            console.log('Tenant (' + tenant.id + ') migration completed');
            this.next();
        }
        return false;
    }.bind(this))
});

MigrateTestCase.repeatStep(0);

MigrateTestCase.addStep('Looking for preconfigured tenant in destination cloud', function() {
    var context = this.test_case.context, b = context.body;
    console.log('Got the response', b);

    // Looking for predefined tenant in the destination cloud
    var t = this.test_case.findTenant(b.destination);
    if (t) {
        context.new_tenant = t;
        context.destination_cloud = b.destination;
        return this.next();
    }
    this.fail('Unable to find tenant "' + Config.tenant + '" in destination cloud');
});

MigrateTestCase.getTenantServers = function(tenant_id, cloud) {
    var servers = {}, images = {}, floating_ips = {};
    for (var i in cloud.images) 
        images[cloud.images[i].id] = cloud.images[i];

    for (var i in cloud.floating_ips) {
        var ip = cloud.floating_ips[i];
        if (!floating_ips[ip.server_id]) floating_ips[ip.server_id] = [];
        floating_ips[ip.server_id].push(ip.id);
    }

    for (var i in cloud.servers) 
        if (cloud.servers[i].tenant_id == tenant_id) {
            var s = cloud.servers[i];
            // Assigning image
            if (s.image_id) s.image_name = images[s.image_id].name;
            else s.image_name = '';
            // Assigning all floating ips
            if (floating_ips[s.id]) s.floating_ips = floating_ips[s.id].sort().join(',');
            else s.floating_ips = '';
            
            servers[s.name] = s;
        }
    return servers;
}; 

MigrateTestCase.assureServersEqual = function(s1, s2) {
    for (var i in s1) {
        var s = s1[i], so = s2[i];
        console.log(i, s, so);
        if (!so) this.fail('Unable to find server "' + s.name + '"');
        if (s.image_name != so.image_name) this.fail('Server "' + s.name + '" uses different image ("' + s.image_name + '" vs "' + so.image_name + '")');
        if (s.floating_ips != so.floating_ips) this.fail('Server "' + s.name + '" has different set of floating ips ("' + s.floating_ips + '" vs "' + so.floating_ips + '")');
    }
};

MigrateTestCase.addStep('Making sure tenants are equal', function() {
    var context = this.test_case.context,
        old = context.tenant, 
        now = context.new_tenant,
        src = context.source_cloud,
        dst = context.destination_cloud;

    // Making sure tenants are equal
    if (old.description != now.description) this.fail('Tenants descriptions differ');

    // Checking that all entities that relate to these tenants are the same
    var src_servers = this.test_case.getTenantServers(old.id, src);
    var dst_servers = this.test_case.getTenantServers(now.id, dst);

    console.log('Validating all servers along with images and floating ips');
    this.test_case.assureServersEqual(src_servers, dst_servers);
    this.test_case.assureServersEqual(dst_servers, src_servers);
    
    this.next();
    
});

exports.o = MigrateTestCase;
