Functional tests suite for Pumphouse
====================================

This set of scripts represents simple suite for functional testing of the Pumphouse project via REST API it exposes and SocketIO bus it reports states to. It is implemented as several test-case modules and runner script implemented on node.js.

# Prerequisites

## Node.js installation

In order to install node.js below instructions should be followed:

```sh
git clone git://github.com/ry/node.git
cd node*
./configure
make
make install
```

## Node.js packages involved

All node.js dependencies are specified in `package.json`. These are:

* `"superagent": "~0.19.1"`
* `"socket.io-client": "~0.9.16"`

In order to install all dependencies the following should be executed in the same folder with `package.json`:

```sh
npm install
```

## Package contents

Suite consists of the following major parts:

* `api.js`
    Wrapper over the Pumphouse' REST API

* `events.js`
    SocketIO events listener and handlers manager

* `config.js`
    Suite configuration

* `test_case.js`
    Base class for all test-cases, test steps they consist of and execution logic

* `case_reset.js`
    Environment reset (cleanup/setup) test-case

* `case_migrate.js`
    Tenant evacuation test-case. It reads initial tenant configuration, initiates its migration and asserts destination configuration equals to the initial one

* `case_evaculate.js`
    Host evacuation test-case. It reads initial host configuration (list of servers it hosts), initiates evacuation and asserts that host does not host any servers while all the servers it hosted initially are moved across other hosts

* `index.js`
    Main execution script

* `package.json`
    Package descriptor

* `README.md`
    This document

# Configuration

The following values are defined in config.js module:

* `endpoint`
    E.g.: `http://localhost:3002`
    Base URL of Pumphouse API. It is expected that SocketIO bus is created on ``/events`` location

* `timeout`
    E.g.: `120`
    Period of time (in seconds) after which execution of tests interrupted by timeout

* `cases`
    Default: `['reset', 'migrate', 'evaculate', 'reassign']`
    Ordered list of test-cases to be executed

* `tenant-name-mask`
    E.g.: `pumphouse-`
    Name mask to be used while searching for the tenant to migrate. NOTE, mask should match from the beginning of the tenant name

# Tests execution

To start tests execution run

```sh
    node index
```

Test-cases will be executed in the following sequence:

1. `case_reset`
2. `case_migration`
3. `case_evaculation`
4. `case_reassignment`

All outputs are redirected to `STDOUT`.

Exit code should be analyzed for the execution result.
