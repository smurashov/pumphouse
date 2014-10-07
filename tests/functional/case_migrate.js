var TestCase = require('./test_case');
var Config = require('./config');

var MigrateTestCase = new TestCase('Tenant migration');

MigrateTestCase.addStep('Calling API to fetch resources', function() {
    var that = this;
    this.test_case.api.resources(function(err, res) {
        if (err) that.fail('Resources fetching error');
        that.test_case.context.body = res.body;
        that.next();
    })
});

MigrateTestCase.addStep('Looking for preconfigured tenant', function() {
    var b = this.test_case.context.body;
    console.log('Got the response', b);

    // Looking for predefined tenant in the source cloud
    for (var j = 0, l = b.source.tenants.length; j < l; j++) {
        var t = b.source.tenants[j];
        if (t.name === Config.tenant) {
            this.test_case.context.tenant = t;
            console.log('Found tenant: ', t);
            return this.next();
        }
    }
    this.fail('Unable to find tenant');
});

MigrateTestCase.addStep('Initiate tenant migration', function() {
    var that = this, tenant = this.test_case.context.tenant;
    this.test_case.api.migrateTenant(tenant.id, function(err, res) {
        if (err) that.fail('Tenant (' + tenant.id + ') migration initialization failed');
        that.next();
    })
});

MigrateTestCase.addStep('Listening for tenant migrated event', function() {
    var that = this, tenant = this.test_case.context.tenant;
    this.test_case.events.on('tenant migrated', function(m) {
        if (m.id == tenant.id) {
            console.log('Tenant (' + tenant.id + ') migration completed');
            that.test_case.context.old_tenant = tenant;
            that.next();
        }
        return false;
    })
});

MigrateTestCase.repeatStep(0);

MigrateTestCase.repeatStep(1);

MigrateTestCase.addStep('Making sure tenants are equal', function() {
    var old = JSON.stringify(this.test_case.context.old_tenant), 
        now = JSON.stringify(this.test_case.context.tenant);

    if (old !== now) this.fail('Tenants before (' + old + ') and after (' + now + ') migration are not equal');
    else this.next();
    
});

exports.o = MigrateTestCase;
