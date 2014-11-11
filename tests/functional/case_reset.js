var TestCase = require('./test_case');

var ResetTestCase = new TestCase('Environments reset');

ResetTestCase.addStep('Calling API to reset', function() {
    this.test_case.api.reset(function(err, res) {
        if (err) this.fail('Resetting error');
        this.next();
    }.bind(this));
});

ResetTestCase.addStep('Fetching reset completion events for both clouds', function() {
    var completed_for = {};
    this.test_case.events.on('reset completed').execute(function(m) {
        console.log(m);
        completed_for[m.cloud] = true;
        if (completed_for['source'] && completed_for['destination']) {
            console.log('Reset completed');
            return this.next();
        }
        return false;
    }.bind(this))
});

exports.testcase = ResetTestCase;
