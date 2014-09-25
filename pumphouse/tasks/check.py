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

from pumphouse import checks
from pumphouse import exceptions
from pumphouse import task

from taskflow.patterns import linear_flow


LOG = logging.getLogger(__name__)


class RunCheck(task.BaseCloudTask):
    def execute(self, server_info, command):
        check_config = {
            "input": self._get_ip_list(server_info),
            "env": {},
            "cmd": command
        }
        check = checks.PumpHouseShellCheck(check_config)
        try:
            result = check.run()
        except exceptions.CheckError as exc:
            LOG.exception("Check failed: %s", exc.message)
            raise
        else:
            return True

    def _get_ip_list(self, server_info):
        ip_list = []
        nets = server_info["addresses"]
        addresses = [nets[label] for label in nets]
        for ip in addresses:
            ip_list.append(ip["addr"])
        return ip_list


def run_checks(context, store, server_id, commands=None):
    if not commands:
        commands = []
    flow = linear_flow.Flow("check-server-{}".format(server_id))
    server_ensure = "server-{}-boot".format(server_id)
    for num, command in enumerate(commands):
        check_binding = "check-server-{}-{}".format(server_id, num)
        command_binding = "check-command-{}-{}".format(server_id, num)
        flow.add(RunCheck(context.src_cloud,
                          name=check_binding,
                          provides=check_binding,
                          rebind=[server_ensure,
                                  command_binding]))
        store[command_binding] = command
    return flow, store
