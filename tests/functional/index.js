var Config = require('./config');
var Listener = require('./events');
var API = require('./api');

var events = new Listener(Config.endpoint + '/events').bindHandlers();
pumphouse = new API(Config.endpoint);

setTimeout(function() {process.exit(code=1)}, 120000);

pumphouse.reset(function() {
    console.log('Reset event emitted');
    var completed_for = {};
    events.on('reset completed', function(m) {
        completed_for[m.cloud] = true;
        if (completed_for['source'] && completed_for['destination']) {
            console.log('Reset completed');
            events.disconnect();
            process.exit(code=0);
        }
        return false;
    })
});
