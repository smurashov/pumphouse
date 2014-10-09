var io = require('socket.io-client');

function EventsListener(path) {
    this.socket = io.connect(path);     // 'http://localhost:3002/events'

    this.event_data = [];
    this._waiters = {};

    return this;
};

EventsListener.prototype.disconnect = function() {
    this.socket.disconnect();
};

EventsListener.prototype.logEventData = function(name, message) {
    console.log('Event "' + name + '": ' + message);
    this.event_data.push((name, message));
};

EventsListener.prototype.checkWaiters = function(name, m) {
    var w = this._waiters[name];
    if (w) {
        this._waiters[name] = w.reduce(
            function(p, c) {
                if (!c(m)) p.push(c);
                return p;
            }, []);
    }
    //console.log(this._waiters);
};

EventsListener.prototype.handlerFactory = function(name) {
    var that = this;
    return function(m) {
        that.checkWaiters(name, m);
        that.logEventData(name, JSON.stringify(m));
    };
};

EventsListener.prototype.on = function(event, handler) {
    if (!this._waiters[event]) this._waiters[event] = [];
    this._waiters[event].push(handler);
};

EventsListener.prototype.bindHandlers = function() {
    [
        'connected',
        'disconnected',
        'tenant migrate',
        'tenant create',
        'tenant migrated',
        'image created',
        'image upload',
        'image uploading',
        'image uploaded',
        'server migrate',
        'server suspend',
        'server boot',
        'server terminate',
        'server activate',
        'server migrated',
        'reset started',
        'reset completed'
    ].map(function(name) {
        this.socket.on(name, this.handlerFactory(name))
    }, this);
    return this;
};

module.exports = EventsListener;
