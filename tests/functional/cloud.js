/*jslint node:true*/
/*jslint plusplus:true*/
/*jslint evil: true*/

'use strict';

function CloudResources(data) {
    this.resources = {};
    this.length = 0;

    this.parseCloud('source', data);
    this.parseCloud('destination', data);

    //console.log(JSON.stringify(this.resources));
}

CloudResources.prototype.toString = function () {
    return '{CloudResources[' + this.length + ']}';
};

CloudResources.prototype.getKey = function (data) {
    return [data.type, data.cloud, data.id].join('-');
};

CloudResources.prototype.parseCloud = function (name, data) {
    var i,
        o,
        key,
        r = data[name].resources;

    console.log('Parsing ' + name + ' cloud data:');
    for (i in r) {
        if (r.hasOwnProperty(i)) {
            try {
                o = r[i];
                //o.cloud = name;
                key = this.getKey(o);
                this.resources[key] = o;
                this.length++;
            } catch (e) {
                console.error('Unable to parse object', o);
            }
        }
    }
    console.log('Cloud resources: ', this.resources);
};

CloudResources.prototype.get = function (id, type, cloud) {
    if (arguments.length === 3) {
        return this.resources[this.getKey({
            'id': id,
            'type': type,
            'cloud': cloud
        })];
    } else {
        return this.resources[this.getKey(id)];
    }
};

CloudResources.prototype.getAll = function (params) {
    var s = '',
        result = [],
        k,
        f;

    for (k in params) {
        if (params.hasOwnProperty(k)) {
            s += (s ? ' && "' : '"') + params[k] + '"===a.' + k;
        }
    }

    f = new Function('a', 'return(' + s + ')');

    for (k in this.resources) {
        if (this.resources.hasOwnProperty(k)) {
            if (f(this.resources[k])) {
                result.push(this.resources[k]);
            }
        }
    }
    return result;
};


module.exports = CloudResources;
