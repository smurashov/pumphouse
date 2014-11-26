/*jslint node:true*/

'use strict';

var io = require('socket.io-client');


/**
 * Handles event addressed to a specific entity
 * @param   {String}       event type
 * @returns {EventHandler} itself for chaining
 */
function EventHandler(event) {
    this.event = event;
    this.entity = {};
    this.data = {};
    this.executions = 1;
    this.handler = function () {
        return true;
    };
    return this;
}

/**
 * Adds parameters for event matching
 * @param   {Object}        entity top-level parameters for matching {type: .., cloud: ...}
 * @param   {Object}        data   second-level parameters {data: {status: ...}}
 * @returns {EventHandlers} itself for chaining
 */
EventHandler.prototype.of = function (entity, data) {
    if (!this.event) {
        console.error('Event name should be defined prior to the entity', entity);
        return null;
    }
    this.entity = entity;
    this.data = data || {};
    return this;
};

/**
 * Provides handling function to be executed when matching event received
 * @param {Function} f handler function
 */
EventHandler.prototype.execute = function (f) {
    this.handler = f;
    return this;
};

/**
 * Allows the same handler to be executed multiple times
 * @param {Number} times to be executed
 */
EventHandler.prototype.repeat = function (times) {
    this.executions = times;
    return this;
};




/**
 * Manages socketio events and their handlers
 * @returns {HandlersManager} returns itself for chaining
 */
function HandlersManager() {
    this.handlers = [];
    this.events_bus = [];
    this.listener = null;
    return this;
}

/**
 * Creates new handler for event of given type and adds it to the
 * queue
 * @param   {String}       event name
 * @returns {EventHandler} EventHandler object for further matching conditioning
 */
HandlersManager.prototype.listenFor = function (event) {
    var h = new EventHandler(event);
    this.handlers.push(h);
    return h;
};

/**
 * Intercepts allowed events and keeps them internally
 * @param {String} event_name name of event
 * @param {Object} data       passed along with event
 */
HandlersManager.prototype.intercept = function (event_name, data) {
    var entity_data = data.hasOwnProperty('data') ? data.data : {};
    delete data.data;
    this.events_bus.push({
        'name': event_name,
        'entity': data,
        'data': entity_data
    });
    console.log('Received event: ', event_name, JSON.stringify(data));
};

HandlersManager.prototype.match = function () {
    console.log('Handlers: ', JSON.stringify(this.handlers));
    if (!this.handlers.length) {
        this.startListening();
        return false;
    }

    var event,
        handler = this.handlers[0],
        k,
        match = true;

    console.log('Looking for matches for: ', JSON.stringify(handler));

    while (this.events_bus.length) {
        event = this.events_bus.shift();
        if (event.name === handler.event) {
            // Check if event has all the values handler requires
            for (k in handler.entity) {
                if (handler.entity.hasOwnProperty(k)) {
                    if (!event.entity.hasOwnProperty(k) || handler.entity[k] !== event.entity[k]) {
                        match = false;
                    }
                }
            }

            if (match) {
                // Check if datas are matched
                if (event.data.length || handler.data.length) {
                    for (k in handler.data) {
                        if (handler.data.hasOwnProperty(k)) {
                            if (!event.data.hasOwnProperty(k) || handler.data[k] !== event.data[k]) {
                                match = false;
                            }
                        }
                    }
                }
            }

            if (match) {
                // Event matched to the handler
                // Handling funtion is executed with the event data
                console.log('Match found: ', JSON.stringify(event));

                handler.executions -= 1;
                if (handler.handler(event) && !handler.executions) {
                    this.handlers.shift();
                }
                return true;
            }
        }
    }
    this.startListening();
};

/**
 * Starts matching handlers to events received.
 */
HandlersManager.prototype.startListening = function () {
    this.listener = setTimeout(this.match.bind(this), 1000);
};




/**
 * Listener of socketio events
 * @param   {String}        path to socketio endpoint
 * @returns {EventListener} returns newly created instance for chaining
 */
function EventsListener(path) {
    this.socket = io.connect(path);

    this.handlers = new HandlersManager();

    [
        'create',
        'update',
        'delete',

        'error',

        'reset start',
        'reset completed'
    ].map(function (name) {
        this.socket.on(name, this.handlerFactory(name));
    }, this);

    return this.handlers;
}

/**
 * Forces disconnection from socket
 */
EventsListener.prototype.disconnect = function () {
    this.socket.disconnect();
};

EventsListener.prototype.handlerFactory = function (event_name) {
    return function (data) {
        console.log('Event "' + event_name + '": ' + JSON.stringify(data));
        this.handlers.intercept(event_name, data);
    }.bind(this);
};

module.exports = EventsListener;
