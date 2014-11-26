/*jslint node:true*/

'use strict';

module.exports = {
    endpoint: 'http://localhost:3002',
    timeout: 120,
    cases: [
        'reset',
        'migrate',
        'evaculate',
        'reassign'
    ],
    tenant_name_mask: 'pumphouse-'
};
