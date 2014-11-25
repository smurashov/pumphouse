var TestCase = require('./test_case');
var Config = require('./config');
var Cloud = require('./cloud');

var ReassignTestCase = new TestCase('Host reassignment');

ReassignTestCase.addStep('Calling API to fetch resources', function () {
    this.test_case.api.resources(function (err, res) {
        if (err) this.fail('Resources fetching error');

        this.test_case.context.state = new Cloud(res.body);
        return this.next();
    }.bind(this))
});

ReassignTestCase.addStep('Looking for preconfigured host in source cloud', function () {
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

ReassignTestCase.addStep(
    'Initiate host reassignment and listening for host reassignment start event',
    function () {
        var host = this.test_case.context.host;

        this.test_case.events
            .on('update')
            .of(Config.host)
            .execute(
                function (m) {
                    if (m.action == 'reassignment') {
                        console.log('Host ' + host.id + ' reassignment started');
                        return this.next();
                    }
                    return false;
                }.bind(this)
            );

        this.test_case.api.reassignHost(host.id, function (err, res) {
            if (err) this.fail('Host ' + host.id + ' reassignment initialization failed');

            return this.next();
        }.bind(this));
    }
);

ReassignTestCase.addStep('Listening for host deletion event', function () {
    var host = this.test_case.context.host;

    this.test_case.events
        .on('delete')
        .of(Config.host)
        .execute(
            function (m) {
                console.log('Host ' + host.id + ' deleted');
                return this.next();
            }.bind(this)
        )
});

ReassignTestCase.addStep('Listening for host creation event', function () {
    var context = this.test_case.context;

    this.test_case.events
        .on('create')
        .execute(function (m) {
            if (m.type == 'host' &&
                m.cloud == 'destination' &&
                m.action == 'reassignment') {
                console.log('Host ' + m.id + ' has been created in destination cloud');
                context.new_host = m;
                return this.next();
            }
            return false;
        }.bind(this))
});

ReassignTestCase.addStep('Listening for host reassignment completion event', function () {
    var new_host = this.test_case.context.new_host;

    this.test_case.events
        .on('update')
        .of(new_host)
        .execute(function (m) {
            if (m.action == '') {
                console.log('Host ' + m.id + ' reassignment completed');
                return this.next();
            }
            return false;
        }.bind(this))
});

ReassignTestCase.addStep('Saving previous cloud configuration', function () {
    this.test_case.context.initial_state = this.test_case.context.state;
    return this.next();
});

ReassignTestCase.repeatStep(0);

ReassignTestCase.normalizeHosts = function (hosts) {
    var result = {};
    for (var i in hosts) result[hosts[i].id] = hosts[i];
    return result;
};

ReassignTestCase.compare = function (s1, s2, cloud, exclusion) {
    var diff_found = false;
    for (var i in s1) {
        h = s1[i];
        if (h.cloud != cloud) continue;
        if (!s2[i]) {
            if (h.id != exclusion.id) {
                this.fail('Expected difference: ' + exclusion.data.name + ', actual: ' + h.data.name);
            } else {
                console.log(' - Expected difference: ' + exclusion.data.name);
                diff_found = true;
            }
        } else console.log(' - Host ' + h.data.name + ' found in both sets');
    }
    if (!diff_found) this.fail('Expected difference ' + exclusion.data.name + ' not found');
};

ReassignTestCase.addStep('Assuring host is removed from source cloud and new one added to destination', function () {
    var context = this.test_case.context,
        host = context.host,
        new_host = context.new_host,
        old = this.test_case.normalizeHosts(context.initial_state.getAll({'type': 'host'})),
        now = this.test_case.normalizeHosts(context.state.getAll({'type': 'host'})),
        h;

    console.log('Assure ' + host.data.name + ' is the only difference between initial and resulting source cloud hosts configuration');
    this.test_case.compare(old, now, 'source', host);

    console.log('Assure ' + new_host.data.name + ' is the only difference between initial and resulting destination cloud hosts configuration');
    this.test_case.compare(now, old, 'destination', new_host);

    return this.next();
});

exports.testcase = ReassignTestCase;
