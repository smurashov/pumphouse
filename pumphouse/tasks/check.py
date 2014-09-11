from pumphouse import checks
from pumphouse import exceptions
from pumphouse import task

from taskflow.patterns import unordered_flow


class RunCheckTask(task.BaseCloudTask):
    def execute(self, server_info, commands):
        for command in commands:
            check_config = {
                "input": self._get_ip_list(server_info),
                "env": {},
                "cmd": command
            }
            check = checks.PumpHouseShellCheck(check_config)
            result = check.run()
            if not result:
                raise exceptions.CheckError("Unknown")
        return True

    def _get_ip_list(self, server_info):
        ip_list = []
        nets = server_info["addresses"]
        addresses = [nets[label] for label in nets]
        for ip in addresses:
            ip_list.append(ip["addr"])
        return ip_list


def run_checks(src, dst, store, server_id, commands=None):
    server_ensure = "server-{}-boot".format(server_id)
    check_binding = "checks-{}".format(server_id)
    commands_binding = "check-commands-{}".format(server_id)
    flow = unordered_flow.Flow("checks-{}".format(server_id))
    task = RunCheckTask(src,
                        name=check_binding,
                        provides=check_binding,
                        rebind=[server_ensure,
                                commands_binding])
    store[commands_binding] = commands
    return task, store
