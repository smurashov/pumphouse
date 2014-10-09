var TestCase = require('./test_case');

var ResetTestCase = new TestCase('Environments reset');

ResetTestCase.addStep('Calling API to reset', function() {
    var that = this;
    this.test_case.api.reset(function(err, res) {
        if (err) that.fail('Resetting error');
        that.next();
    })
});

ResetTestCase.addStep('Fetching reset completion events for both clouds', function() {
    var completed_for = {}, that = this;
    this.test_case.events.on('reset completed', function(m) {
        completed_for[m.cloud] = true;
        if (completed_for['source'] && completed_for['destination']) {
            console.log('Reset completed');
            return that.next();
        }
        return false;
    })
});

exports.o = ResetTestCase;
