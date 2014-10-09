var Config = require('./config');
var Listener = require('./events');
var API = require('./api');

var events = new Listener(Config.endpoint + '/events').bindHandlers();
var pumphouse = new API(Config.endpoint);


var cases = ['reset', 'migrate'], limit = 120, i = 0, completed = true, c, timer;

// Async tests runner
setInterval(function() {
    if (completed) {
        cycles = 0;
        if (i >= cases.length) {
            console.log('Tests execution completed');
            process.exit(code=0);
        }
        c = require('./case_' + cases[i++]);
        c.o.run(pumphouse, events);
    }
    completed = c.o.completed;
    if (cycles++ > limit) {
        console.error('Timed out!');
        process.exit(code=1);
    }
    cycles++;
}, 1000);

