var TestCase = require('./test_case');
var Config = require('./config');

var EvacuateTestCase = new TestCase('Tenant migration');

EvacuateTestCase.addStep('Calling API to fetch resources', function() {
    this.test_case.api.resources(function(err, res) {
        if (err) this.fail('Resources fetching error');
        this.test_case.context.body = res.body;
        this.next();
    }.bind(this))
});

EvacuateTestCase.findHost = function(cloud) {
    // Looking for predefined tenant in the source cloud
    for (var j = 0, l = cloud.hosts.length; j < l; j++) {
        var h = cloud.hosts[j];
        if (h.name === Config.host) {
            console.log('Found host: ', h.name);
            return h;
        }
    }
    return false
};

EvacuateTestCase.addStep('Looking for preconfigured host in source cloud', function() {
    var context = this.test_case.context, b = context.body;
    console.log('Got the response', b);

    // Looking for predefined tenant in the source cloud
    var h = this.test_case.findHost(b.source);
    if (h) {
        context.host = h;
        context.source_cloud = b.source;
        return this.next();
    }
    this.fail('Unable to find host "' + Config.host + '" in source cloud');
});

EvacuateTestCase.addStep('Initiate host evacuation', function() {
    var host = this.test_case.context.host;
    this.test_case.api.evacuateHost(host.name, function(err, res) {
        if (err) this.fail('Host ' + host.name + ' reassignment initialization failed');
        this.next();
    }.bind(this))
});

EvacuateTestCase.addStep('Listening for host reassigned event', function() {
    var host = this.test_case.context.host;
    this.test_case.events.on('host reassigned', function(m) {
        if (m.name == host.name) {
            console.log('Host ' + host.name + ' reassignment completed');
            this.next();
        }
        return false;
    }.bind(this))
});

EvacuateTestCase.addStep('Saving previous cloud configuration', function() {
    this.test_case.context.old = this.test_case.context.body;
    this.next();
});

EvacuateTestCase.repeatStep(0);

EvacuateTestCase.addStep('Assuring host is clean and all servers live migrated from it', function() {
    var context = this.test_case.context,
        host = context.host, 
        old_servers = context.old.source,
        now_servers = context.body.source

    // Making sure all servers evacuated from host still alive
    for (var i in old_servers) {
        var s = old_servers[i], n = now_servers[i];
        if (!n)
            this.fail('Unable to locate server ' + s.name + ' (' + s.id + ') that existed before reassignment');
        if (n.status != 'error' && n.host_name == host.name)
            this.fail('Host still contains servers not in ERROR state (' + n + ')');
    }
    this.next();
});

exports.o = EvacuateTestCase;
