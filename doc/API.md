FORMAT: 1A
HOST: http://www.pumphouse.com

# Pumphouse API
This document describes API of the Pumphouse service. The service provides a functionaly for migrating workloads (i.e. tenants and their resources) from arbitrary OpenStack cloud to Mirantis OpensStack cloud.

# Pumphouse resources
Collection of resources.

## List resources of both source and destination clouds [/resources]
### List resources [GET]
+ Response 200 (application/json)

        {
            "reset": false,
            "source": {
                "urls": {
                    "horizon": "192.168.5.6/horizon"
                },
                "tenants": [
                    {
                        "id": "74b06486e02347198f6ef3eb1eac82cd",
                        "description": "IT Tenant",
                        "name": "it"
                    },
                    {
                        "id": "dff5be1057e44b798715d00a617c32f6",
                        "description": "Services Tenant",
                        "name": "services"
                    },
                    {
                        "id": "0h90hfg98d79g0h789f87gd99x898j7h",
                        "description": "Private Tenant",
                        "name": "private",
                        "status": "migration"
                    }
                ],
                "resources": [
                    {
                        "id": "ca1dd11d-427c-4f62-bcee-13e6773ce0f8",
                        "type": "server",
                        "name": "server-0",
                        "image_id": "88785d30-382a-45a9-9c4e-317306ceae9e",
                        "tenant_id": "74b06486e02347198f6ef3eb1eac82cd",
                        "host_name": "cz5540.host-telecom.com"
                    },
                    {
                        "id": "ca345d11d-427c-44362-bce3-13e473cec53",
                        "type": "server",
                        "name": "server-1",
                        "image_id": "88785d30-382a-45a9-9c4e-317306ceae9e",
                        "tenant_id": "dff5be1057e44b798715d00a617c32f6",
                        "host_name": "cz5548.host-telecom.com"
                    },
                    {
                        "id": "88785d30-382a-45a9-9c4e-317306ceae9e",
                        "type": "image",
                        "name": "cirros-0.3.2-x86_64-uec",
                        "host_name": "cz5548.host-telecom.com",
                        "status": "error"
                    }
                ],
                "hosts": [
                    {
                        "name": "cz5540.host-telecom.com",
                        "status": "available"
                    },
                    {
                        "name": "cz5550.host-telecom.com",
                        "status": "error"
                    },
                    {
                        "name": "cz5570.host-telecom.com",
                        "status": "evacuation"
                    },
                    {
                        "name": "cz5571.host-telecom.com",
                        "status": "blocked"
                    }
                ]
            },
            "destination": {
                "urls": {
                    "horizon": "192.168.5.7/horizon",
                    "mos": "192.168.5.10"
                },
                "tenants": [],
                "resources": [],
                "hosts": [
                    {
                        "name": "cz5560.host-telecom.com",
                        "status": "available"
                    }
                ]
            },
            "hosts": [],
            "events": [
                "88785d30-382a-45a9-9c4e-81aaeeffbb00",
                "88785d30-382a-45a9-9c4e-678134eeffaa"
            ]
        }


## Reset the state of the clouds [/reset]
The endpoint available only if the "reset" key is present in the state of the world and is equal to true. Otherwise the endpoint returns the 404 status.
### Send the reset request [POST]
+ Response 201


## Migration events of tenants [/events/{event_id}]
### Pull a stream of events [GET]
+ Response 200

    Server migration

    + Headers

            Connection: keep-alive
            Content-Type: text/event-stream
            Transfer-Encoding: chunked
    
    + Body
    
            {
                'event': 'server migrate',
                'data': {'id': '74b06486e02347198f6ef3eb1eac82cd'}
            },
            {
                'event': 'server suspended',
                'data': {'id': '74b06486e02347198f6ef3eb1eac82cd', 'cloud': 'source'}
            },
            {
                'event': 'server resumed',
                'data': {'id': '74b06486e02347198f6ef3eb1eac82cd', 'cloud': 'source'}
            },
            {
                'event': 'server boot',
                'data': {'id': 'ca1dd11d-427c-4f62-bcee-13e6773ce0f8', 'cloud': 'destination', 'name': 'server-4', 'tenant_id': '74b06486e02347198f6ef3eb1eac82cd', 'image_id': '88785d30-382a-45a9-9c4e-317306ceae9e', 'host_name': 'cz5560.host-telecom.com', 'status': 'active'}
            },
            {
                'event': 'server terminate',
                'data': {'id': '74b06486e02347198f6ef3eb1eac82cd', 'cloud': 'source'}
            },
            {
                'event': 'server migrated',
                'data': {'source_id': '74b06486e02347198f6ef3eb1eac82cd', 'destination_id': 'ca1dd11d-427c-4f62-bcee-13e6773ce0f8'}
            }


# Group Tenants
Operations with Tenants

## Single Tenant Operations [/tenants/{tenant_id}]
### Initiate Tenant Migration [POST]
+ Response 201 (application/json)


# Group Hosts
Operations with Hosts

## Evacuate a Host [/hosts/{host_id}]
### Evacuate a Host [POST]
+ Response 201

### Reassigne a Host from the source cloud to the destination cloud [DELETE]
+ Response 201
