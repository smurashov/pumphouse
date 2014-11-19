module.exports = {
    endpoint: 'http://localhost:3002',
    timeout: 120,
    cases: [
        'reset',
        'migrate',
        'evaculate',
        'reassign'
    ],
    tenant: {
        'id': '74b06486e02347198f6ef3eb1eac82cd',
        'type': 'tenant',
        'cloud': 'source'
    },
    host: {
        'id': 'host1_id',
        'type': 'host',
        'cloud': 'source'
    }
};
