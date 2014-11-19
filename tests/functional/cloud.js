function CloudResources(data) {
    this.resources = {};
    this.length = 0;

    this.parseCloud('source', data);
    this.parseCloud('destination', data);

    //console.log(JSON.stringify(this.resources));
};

CloudResources.prototype.toString = function () {
    return '{CloudResources[' + this.length + ']}';
};

CloudResources.prototype.getKey = function (data) {
    return [data['type'], data['cloud'], data['id']].join('-');
};

CloudResources.prototype.parseCloud = function (name, data) {
    var i, o;
    for (i in data[name]['resources']) {
        try {
            o = data[name]['resources'][i];
            o['cloud'] = name;
            this.resources[this.getKey(o)] = o;
            this.length++;
        }
        catch (e) {
            console.error('Unable to parse object', o);
        }
    }
};

CloudResources.prototype.get = function (id, type, cloud) {
    if (arguments.length == 3) {
        return this.resources[this.getKey({
            'id': id,
            'type': type,
            'cloud': cloud
        })];
    } else {
        return this.resources[this.getKey(id)];
    }
};

CloudResources.prototype.getAll = function(params) {
    var s = '', result = [];
    for (k in params) s += (s ? ' && "': '"') + params[k] + '"==a.' + k;
    var f = new Function('a', 'return(' + s + ')');

    for (var j in this.resources)
        if (f(this.resources[j]))
            result.push(this.resources[j]);
    return result;
};


module.exports = CloudResources;
