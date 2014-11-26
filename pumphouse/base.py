# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.

import logging

from pumphouse.tasks import base
from pumphouse.tasks import reset


LOG = logging.getLogger(__name__)


class Service(object):
    default_num_tenants = 2
    default_num_servers = 2

    def __init__(self, config, plugins, target, cloud_driver, identity_driver):
        self.identity_config = config.pop("identity")
        self.populate_config = config.pop("populate", None)
        self.workloads_config = config.pop("workloads", None)
        self.cloud_urls = config.pop("urls", None)
        self.cloud_config = config
        self.plugins = plugins
        self.target = target
        self.cloud_driver = cloud_driver
        self.identity_driver = identity_driver

    def make(self, identity=None):
        if identity is None:
            identity = self.identity_driver(**self.identity_config)
        cloud = self.cloud_driver.from_dict(self.target, identity,
                                            self.cloud_config)
        LOG.info("Cloud client initialized for endpoint: %s",
                 self.cloud_config["endpoint"]["auth_url"])
        return cloud

    def check(self, cloud):
        return cloud.ping()

    def reset(self, events, cloud):
        try:
            env = reset.Environment(cloud, {})

            runner = base.TaskflowRunner(env)
            cleanup_workload = runner.get_resource(reset.CleanupWorkload,
                                                   {"id": cloud.name})
            runner.add(cleanup_workload.delete)

            populate = self.populate_config
            workloads = self.workloads_config
            if populate is not None or workloads is not None:
                if populate is None:
                    populate = {}
                if workloads is None:
                    workloads = {}
                setup_workload = runner.get_resource(reset.SetupWorkload, {
                    "id": cloud.name,
                    "populate": populate,
                    "workloads": workloads,
                })
                runner.add(setup_workload.create)
            runner.run()
        except Exception:
            LOG.exception("Unexpected exception during cloud reset")

        events.emit("reset completed", {
            "cloud": cloud.name
        }, namespace="/events")
