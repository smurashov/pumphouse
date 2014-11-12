var TestCase = require('./test_case');

var ResetTestCase = new TestCase('Environments reset');

ResetTestCase.addStep('Calling API to reset', function() {
    this.test_case.api.reset(function(err, res) {
        if (err) this.fail('Resetting error');
        this.next();
    }.bind(this));
});

ResetTestCase.addStep('Checking reset started event is sent', function() {
    this.test_case.events
        .on('reset start')
        .execute(function(m) {
            console.log('Reset started event received');
            return this.next();
        }.bind(this))
});

ResetTestCase.addStep('Fetching reset completion events for both clouds', function() {
    var completed_for = {};
    this.test_case.events
        .on('reset completed')
        .execute(function(m) {
            completed_for[m.cloud] = true;
            console.log('Reset completed for ' + m.cloud + ' cloud');

            if (completed_for['source'] && completed_for['destination']) {
                console.log('Reset completed');
                return this.next();
            }
            return false;
        }.bind(this))
});

exports.testcase = ResetTestCase;
