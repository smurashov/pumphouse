var Config = require('./config');
var Listener = require('./events');
var API = require('./api');

var events = new Listener(Config.endpoint + '/events').bindHandlers();
pumphouse = new API(Config.endpoint);

function error(msg) {
    console.error('error: ', msg);
    //process.exit(code=1);
};

cases =  [
    // Reset clouds
    function(callback) {
        pumphouse.reset(function() {
            console.log('Reset api called');
            var completed_for = {};
            events.on('reset completed', function(m) {
                completed_for[m.cloud] = true;
                if (completed_for['source'] && completed_for['destination']) {
                    console.log('Reset completed');
                    return callback();
                }
                return false;
            })
        })
    },

    // Migrate tenant
    function(callback) {
        console.log('Calling api for resources');
        pumphouse.resources(function(err, res) {
            if (err) error(err);
            var b = res.body;
            console.log('Got the response', res.body);

            // Looking for predefined tenant in the source cloud
            for (var j = 0, l = b.source.tenants.length; j < l; j++) {
                var t = b.source.tenants[j];
                if (t.name === Config.tenant) {
                    var tenant = t;
                    console.log('Found tenant to migrate: ', t);
                    pumphouse.migrateTenant(tenant.id, function(err, res) {
                        if (err) error(err);

                        events.on('tenant migrated', function(m) {
                            console.log('***', m.id, tenant.id, m.id == tenant.id);
                            if (m.id == tenant.id) {
                                console.log('Tenant ' + tenant.id + ' migration completed');
                                return callback();
                            }
                            return false;
                        })
                    })
                }
            };
        });
    }
];

var timeout, c = 0;
// Runner function
function run() {
    if (timeout) clearTimeout(timeout);
    //timeout = setTimeout('error(\"Case execution timeout\")', 2400000);

    if (c < cases.length) {
        console.log('-------------- Running case ' + (c + 1) + ' --------------');
        cases[c++](run);
        return true;
    } else {
        console.log('All tests (' + c + ') passed!');
        process.exit(code=0);
    }
};

run();
