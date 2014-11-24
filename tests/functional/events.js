var io = require('socket.io-client');

function HandlersManager(store) {
    this.store = store;
    this.reset();
    return this;
};

HandlersManager.prototype.reset = function (event) {
    this.event = null;
    this.entity = null;
};

HandlersManager.prototype.on = function (event) {
    this.reset();
    this.event = event;
    return this;
};

HandlersManager.prototype.getKey = function (entity) {
    console.log(entity);
    if (entity['type'] && entity['cloud'] && entity['id']) {
        return [entity['type'], entity['cloud'], entity['id']].join('-');
    } else {
        //console.error('Unable to combine key for ', entity);
        return null;
    }
};

HandlersManager.prototype.of = function (entity) {
    if (!this.event) {
        console.error('Event name should be defined prior to the entity', entity);
        return false;
    }
    this.entity = this.getKey(entity);
    return this;
};

HandlersManager.prototype.execute = function (f) {
    if (this.event) {
        if (!this.store[this.event]) {
            this.store[this.event] = {
                null: []
            };
        };
        if (this.entity && !this.store[this.entity]) {
            this.store[this.event][this.entity] = [];
        };
        this.store[this.event][this.entity].push(f);
        return true;
    } else {
        return false;
    }
};

HandlersManager.prototype.handle = function (event_name, data) {
    if (this.store[event_name]) {
        var key = this.getKey(data),
            event_handlers = this.store[event_name] || {null: []},
            entity_event_handlers = event_handlers[key] || [],
            i = entity_event_handlers.length - 1;

        for (; i >= 0; i--) {
            console.log('Handling', key, event_name);
            if (entity_event_handlers[i](data) && key) {
                console.log('Cleaning', event_name, 'handler for', key);
                entity_event_handlers.splice(i, 1);
            }
        };
        // For all entities common handler should also be executed
        if (key && event_handlers[null] && event_handlers[null][0]) event_handlers[null][0](data);
    }
};

/**
 * Listener of socketio events
 * @param   {String}        path to socketio endpoint
 * @returns {EventListener} returns newly created instance for chaining
 */
function EventsListener(path) {
    this.socket = io.connect(path);

    var waiters = {};
    this.handlers = new HandlersManager(waiters);

    [
        'create',
        'update',
        'delete',

        'reset start',
        'reset completed'
    ].map(function (name) {
        this.socket.on(name, this.handlerFactory(name))
    }, this);

    return this.handlers;
};

/**
 * Forces disconnection from socket
 */
EventsListener.prototype.disconnect = function () {
    this.socket.disconnect();
};

EventsListener.prototype.handlerFactory = function (event_name) {
    return function (data) {
        console.log('Event "' + event_name + '": ' + JSON.stringify(data));
        this.handlers.handle(event_name, data);
    }.bind(this);
};

module.exports = EventsListener;
