var TestCase = require('./test_case');
var Config = require('./config');
var Cloud = require('./cloud');

var EvacuateTestCase = new TestCase('Host evacuation');

EvacuateTestCase.addStep('Calling API to fetch resources', function() {
    this.test_case.api.resources(function(err, res) {
        if (err) this.fail('Resources fetching error');

        this.test_case.context.state = new Cloud(res.body);
        return this.next();
    }.bind(this))
});

EvacuateTestCase.addStep('Looking for preconfigured host in source cloud', function() {
    var context = this.test_case.context,
        b = context.state;

    console.log('Got clouds resources', b.toString());

    // Looking for predefined tenant in the source cloud
    var h = b.get(Config.host);
    if (h) {
        console.log('Host ' + Config.host.id + ' found in source cloud');
        context.host = h;
        return this.next();
    }
    this.fail('Unable to find host "' + Config.host + '" in source cloud');
});

EvacuateTestCase.addStep('Initiate host evacuation', function() {
    var host = this.test_case.context.host;

    this.test_case.api.evacuateHost(host.id, function(err, res) {
        if (err) this.fail('Host ' + host.id + ' evacuation initialization failed');

        return this.next();
    }.bind(this))
});

EvacuateTestCase.addStep('Listening for host evacuation start event', function() {
    var host = this.test_case.context.host;

    this.test_case.events
        .on('update')
        .of(Config.host)
        .execute(
            function(m) {
                if (m.action == 'evacuation') {
                    console.log('Host ' + host.id + ' evacuation started');
                    return this.next();
                }
                return false;
            }.bind(this)
        )
});

EvacuateTestCase.addStep('Listening for host evacuation finish event', function() {
    var host = this.test_case.context.host;

    this.test_case.events.on('update').of(Config.host).execute(function(m) {
        if (m.action == '') {
            console.log('Host ' + host.name + ' evacuation completed');
            return this.next();
        }
        return false;
    }.bind(this))
});

EvacuateTestCase.addStep('Saving previous cloud configuration', function() {
    this.test_case.context.initial_state = this.test_case.context.state;
    return this.next();
});

EvacuateTestCase.repeatStep(0);

EvacuateTestCase.addStep('Assuring host is clean and all servers live migrated from it', function() {
    var context = this.test_case.context,
        host = context.host,
        old = context.initial_state.getAll({'type': 'server', 'data.host_id': host.id}),
        now = context.state

    // Making sure all servers evacuated from host still alive
    for (var i in old) {
        var s = old[i], n = now.get(s);
        console.log(' - Server ' + s.data.name + ': ' + s.data.host_id + ' -> ' + n.data.host_id);
        if (!n) {
            this.fail('Unable to locate server ' + s.name + ' (' + s.id + ') existed before evacuation');
        } else if (n.data.host_id == host.id) {
            this.fail('Host still contains server: ' + n.data.name + ' (' + n.id + ')');
        }
    }
    return this.next();
});

exports.testcase = EvacuateTestCase;
