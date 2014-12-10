/*jslint node:true*/

'use strict';

var TestCase = require('./test_case');
var Cloud = require('./cloud');

var EvacuateTestCase = new TestCase('Host evacuation');

EvacuateTestCase.addStep('Call /resources API to fetch resources', function () {
    this.test_case.api.resources(function (err, res) {
        if (err) {
            this.fail('Resources fetching error');
        }

        this.test_case.context.state = new Cloud(res.body);
        return this.next();
    }.bind(this));
});

EvacuateTestCase.addStep('Look for preconfigured host in source cloud', function () {
    var context = this.test_case.context,
        res = context.state.resources,
        b = context.state,
        hosts = 0,
        host,
        i,
        j;

    console.log('Got clouds resources', b.toString());

    // Looking for the host
    for (i in res) {
        if (res.hasOwnProperty(i)) {
            j = res[i];
            if (j.type === 'host' && j.cloud === 'source') {
                hosts += 1;
                host = j;
            }
        }
    }

    if (hosts <= 1) {
        this.fail('Source cloud has the only ' + hosts + ' hosts. Unable to evacuate.');
    }

    if (host) {
        console.log('Host ' + JSON.stringify(host) + ' picked randomly in source cloud');
        context.host = host;
        return this.next();
    }
    this.fail('Unable to find host in source cloud');
});

EvacuateTestCase.addStep('Initiate host evacuation', function () {
    var host = this.test_case.context.host;

    this.test_case.api.evacuateHost(host.id, function (err, res) {
        if (err) {
            this.fail('Host ' + host.id + ' evacuation initialization failed');
        }
        return this.next();
    }.bind(this));
});

EvacuateTestCase.addStep('Listen for host evacuation start event', function () {
    var host = this.test_case.context.host;

    this.test_case.events
        .listenFor('update')
        .of({
            'id': host.id,
            'type': 'host',
            'cloud': 'source',
            'action': 'evacuation'
        })
        .execute(
            function (m) {
                console.log('Host ' + host.id + ' evacuation started');
                return this.next();
            }.bind(this)
        );

    this.test_case.events.startListening();
});

EvacuateTestCase.addStep('Listen for host evacuation finish event', function () {
    var host = this.test_case.context.host;

    this.test_case.events
        .listenFor('update')
        .of({
            'id': host.id,
            'type': 'host',
            'cloud': 'source',
            'action': null
        })
        .execute(function (m) {
            console.log('Host ' + host.name + ' evacuation completed');
            return this.next();
        }.bind(this));

    this.test_case.events.startListening();
});

EvacuateTestCase.addStep('Saving previous cloud configuration', function () {
    this.test_case.context.initial_state = this.test_case.context.state;
    return this.next();
});

EvacuateTestCase.repeatStep(0);

EvacuateTestCase.addStep('Assuring host is clean and all servers live migrated from it', function () {
    var context = this.test_case.context,
        host = context.host,
        old = context.initial_state.getAll({'type': 'server', 'data.host_id': host.id}),
        now = context.state,
        i,
        s,
        n;

    console.log('Initial state: ', context.initial_state);
    console.log('Resulting state: ', this.test_case.context.state);

    // Making sure all servers evacuated from host still alive
    for (i in old) {
        if (old.hasOwnProperty(i)) {
            s = old[i];
            n = now.get(s);

            if (!n) {
                this.fail('Unable to locate server ' + s.data.name + ' (' + s.id + ') existed before evacuation');
            } else {
                console.log(' - Server ' + s.data.name + ': ' + s.data.host_id + ' -> ' + n.data.host_id);
                if (n.data.host_id === host.id) {
                    this.fail('Host still contains server: ' + n.data.name + ' (' + n.id + ')');
                }
            }
        }
    }
    return this.next();
});

exports.testcase = EvacuateTestCase;
