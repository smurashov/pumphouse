/*jslint node:true*/

'use strict';

var TestCase = require('./test_case');
var Cloud = require('./cloud');

var ReassignTestCase = new TestCase('Host reassignment');

ReassignTestCase.addStep('Call /resources API to fetch resources', function () {
    this.test_case.api.resources(function (err, res) {
        if (err) {
            this.fail('Resources fetching error');
        }

        this.test_case.context.state = new Cloud(res.body);

        return this.next();
    }.bind(this));
});

ReassignTestCase.addStep('Look for BLOCKED host in source cloud', function () {
    var context = this.test_case.context,
        res = context.state.resources,
        b = context.state,
        host,
        i,
        j;

    console.log('Got clouds resources', b.toString());

    // Looking for the blocked host
    for (i in res) {
        if (res.hasOwnProperty(i)) {
            j = res[i];
            if (j.type === 'host' &&
                    j.cloud === 'source' &&
                    j.data.status === 'blocked') {
                host = j;
            }
        }
    }

    if (host) {
        console.log('Blocked host ' + JSON.stringify(host) + ' found in source cloud');
        context.host = host;
        return this.next();
    }
    this.fail('Unable to find blocked host in source cloud');
});

ReassignTestCase.addStep('Initiate host reassignment [POST] /host', function () {
    var host = this.test_case.context.host;

    this.test_case.api.reassignHost(host.id, function (err, res) {
        if (err) {
            this.fail('Host ' + host.id + ' reassignment initialization failed');
        }

        return this.next();
    }.bind(this));
});

ReassignTestCase.addStep('Listen for host reassignment start event', function () {
    var host = this.test_case.context.host;

    this.test_case.events
        .listenFor('update')
        .of({
            'id': host.id,
            'type': 'host',
            'cloud': 'source',
            'action': 'reassignment'
        })
        .execute(
            function (m) {
                console.log('Host ' + host.id + ' reassignment started');
                return this.next();
            }.bind(this)
        );

    this.test_case.events.startListening();
});

ReassignTestCase.addStep('Listen for host deletion event', function () {
    var host = this.test_case.context.host;

    this.test_case.events
        .listenFor('delete')
        .of({
            'id': host.id,
            'type': 'host',
            'cloud': 'source'
        })
        .execute(
            function (m) {
                console.log('Host ' + host.id + ' deleted');
                return this.next();
            }.bind(this)
        );

    this.test_case.events.startListening();
});

ReassignTestCase.addStep('Listen for host creation event', function () {
    var context = this.test_case.context;

    this.test_case.events
        .listenFor('create')
        .of({
            'type': 'host',
            'cloud': 'destination',
            'action': 'reassignment'
        })
        .execute(function (m) {
            console.log('Host ' + m.entity.id + ' has been created in destination cloud');
            context.new_host = m.entity;
            context.new_host.data = m.data;
            return this.next();
        }.bind(this));

    this.test_case.events.startListening();
});

ReassignTestCase.addStep('Listen for host reassignment completion event', function () {
    var new_host = this.test_case.context.new_host;

    this.test_case.events
        .listenFor('update')
        .of({
            'id': new_host.id,
            'type': 'host',
            'cloud': 'destination',
            'action': ''
        })
        .execute(function (m) {
            console.log('Host ' + m.entity.id + ' reassignment completed');
            return this.next();
        }.bind(this));

    this.test_case.events.startListening();
});

ReassignTestCase.addStep('Saving previous cloud configuration', function () {
    this.test_case.context.initial_state = this.test_case.context.state;
    return this.next();
});

ReassignTestCase.repeatStep(0);

ReassignTestCase.normalizeHosts = function (hosts) {
    var result = {},
        i;
    for (i in hosts) {
        if (hosts.hasOwnProperty(i)) {
            result[hosts[i].id] = hosts[i];
        }
    }
    return result;
};

ReassignTestCase.compare = function (s1, s2, cloud, exclusion) {
    var diff_found = false, i, h;
    for (i in s1) {
        if (s1.hasOwnProperty(i)) {
            h = s1[i];
            if (h.cloud === cloud) {
                if (!s2[i]) {
                    if (h.id !== exclusion.id) {
                        this.fail('Expected difference: ' + exclusion.data.name + ', actual: ' + h.data.name);
                    } else {
                        console.log(' - Expected difference: ' + exclusion.data.name);
                        diff_found = true;
                    }
                } else {
                    console.log(' - Host ' + h.data.name + ' found in both sets');
                }
            }
        }
    }
    if (!diff_found) {
        this.fail('Expected difference ' + exclusion.data.name + ' not found');
    }
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
