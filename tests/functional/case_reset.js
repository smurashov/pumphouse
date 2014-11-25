/*jslint node:true*/

'use strict';

var TestCase = require('./test_case');

var ResetTestCase = new TestCase('Environments reset');

ResetTestCase.addStep('Handle reset started event', function () {
    this.test_case.events
        .listenFor('reset start')
        .execute(function (m) {
            console.log('Reset started event received');
            return this.next();
        }.bind(this));

    this.next();
});

ResetTestCase.addStep('Call API to reset', function () {
    this.test_case.api.reset(function (err, res) {
        if (err) {
            this.fail('Resetting error');
        }
    }.bind(this));

    this.test_case.events.startListening();
});

ResetTestCase.addStep('Fetch reset completion events for both clouds', function () {
    var completed_for = {};

    this.test_case.events
        .listenFor('reset completed')
        .repeat(2)
        .execute(function (m) {
            completed_for[m.entity.cloud] = true;
            console.log('Reset completed for ' + m.entity.cloud + ' cloud');

            if (completed_for.source && completed_for.destination) {
                console.log('Reset completed');
                return this.next();
            } else {
                this.test_case.events.startListening();
            }
            return false;
        }.bind(this));

    this.test_case.events.startListening();
});

exports.testcase = ResetTestCase;
