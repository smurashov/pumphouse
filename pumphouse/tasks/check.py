from pumphouse import checks
from pumphouse import exceptions
from pumphouse import task

from taskflow.patterns import linear_flow


class RunChecksTask(task.BaseCloudTask):
    def execute(self, server_info, command):
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


def run_dst_checks(src, dst, store, server_id, commands):
    server_ensure = "server-{}-ensure".format(server_id)
    flow = unordered_flow.Flow("dst-checks-{}".format(server_id))
    for command in commands:
        check_name = "dst-check-{}-{}".format(server_id, command)
        flow.add(RunChecksTask(dst,
                               name=check_name,
                               provides=check_name,
                               rebind=[server_ensure]))
    return flow, store


def run_src_checks(src, dst, store, server_id, commands):
    server_retrieve = "server-{}-retrieve".format(server_id)
    flow = unordered_flow.Flow("src-checks-{}".format(server_id))
    for command in commands:
        check_name = "src-check-{}-{}".format(server_id, command)
        flow.add(RunCheckTask(src,
                              name=check_name,
                              provides=check_name,
                              rebind=[server_retrieve]))
    return flow, store             
