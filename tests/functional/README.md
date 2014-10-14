====================================
Functional tests suite for Pumphouse
====================================

This set of scripts represents simple suite for functional testing of the Pumphouse project via REST API it exposes and SocketIO bus it reports states to. It is implemented as several test-case modules and runner script implemented on node.js.

Prerequisites
=============

Node.js installation
--------------------

In order to install node.js below instructions should be followed::

    git clone git://github.com/ry/node.git
    cd node*
    ./configure
    make
    make install

Node.js packages involved
-------------------------

All node.js dependencies are specified in ``package.json``. These are:

* "superagent": "~0.19.1"
* "socket.io-client": "~0.9.16"

In order to install all dependencies the following should be executed in the same folder with ``package.json``::

    npm install

Package contents
================

Suite consists of the following major parts:

    api.js
        Wrapper over the Pumphouse' REST API

    events.js
        SocketIO events listener and handlers manager

    config.js
        Suite configuration

    test_case.js
        Base class for all test-cases, test steps they consist of and execution logic

    case_reset.js
        Environment reset (cleanup/setup) test-case

    case_migrate.js
        Tenant evacuation test-case. It reads initial tenant configuration, initiates its migration and asserts destination configuration equals to the initial one

    case_evaculate.js
        Host evacuation test-case. It reads initial host configuration (list of servers it hosts), initiates evacuation and asserts that host does not host any servers while all the servers it hosted initially are moved across other hosts

    index.js
        Main execution script

    package.json
        Package descriptor

    README.md
        This document

Configuration
=============

The following values are defined in config.js module:

    endpoint
        E.g.: ``'http://localhost:3002'``

        Base URL of Pumphouse API. It is expected that SocketIO bus is created on ``/events`` location

    tenant
        E.g.: ``'it'``

        Tenant to be used for migration validation

    host
        E.g.: ``'cz5540.host-telecom.com'``

        Host to be used for evacuation validation


Tests execution
===============

To start tests execution run::

    node index

Test-cases will be executed in the following sequence:

1. case_reset
2. case_migration
3. case_evaculation

All outputs are redirected to STDOUT.

Exit code should be analyzed for the execution result.
