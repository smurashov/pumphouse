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

from taskflow.patterns import graph_flow
from taskflow.patterns import linear_flow
from taskflow import retry

from pumphouse import exceptions
from pumphouse.tasks import server as server_tasks
from pumphouse.tasks import service as service_tasks
from pumphouse.tasks import volume as volume_tasks


LOG = logging.getLogger(__name__)


def evacuate_servers(context, hostname):
    try:
        hypervs = context.src_cloud.nova.hypervisors.search(hostname,
                                                            servers=True)
    except exceptions.nova_excs.NotFound:
        LOG.exception("Could not find hypervisors at the host %r.", hostname)
        raise

    disable_services = "disable-services-{}".format(hostname)
    flow = graph_flow.Flow(disable_services)
    flow.add(service_tasks.DiableServiceWithRollback("nova-compute",
                                                     context.src_cloud,
                                                     name=disable_services,
                                                     provides=disable_services,
                                                     inject={
                                                         "hostname": hostname,
                                                     }))
    for hyperv in hypervs:
        if hasattr(hyperv, "servers"):
            for server in hyperv.servers:
                server_tasks.evacuate_server(context, flow, server["uuid"],
                                             requires=[disable_services])
    return flow


def evacuate_volumes(context, hostname):
    cloud = context.src_cloud
    services = cloud.cinder.services.list(binary="cinder-volume")
    hosts = [s.host for s in services
             if s.host != hostname and s.status == "enabled"]
    volumes = cloud.cinder.volumes.list(search_opts={"all_tenants": 1})
    volumes = [v for v in volumes
               if volume_tasks.get_volume_host(v) == hostname]
    flow = linear_flow.Flow("evacuate-volumes-{}".format(hostname))
    disable_cinder = "disable-cinder-volume-{}".format(hostname)
    flow.add(service_tasks.DiableServiceWithRollback(
        "cinder-volume",
        cloud,
        client="cinder",
        name=disable_cinder,
        provides=disable_cinder,
        inject={"hostname": hostname},
    ))
    for volume in volumes:
        try:
            attachment = volume.attachments[0]
        except IndexError:
            attachment = None
        if attachment:
            detach_volume = "detach-volume-{}".format(volume.id)
            volume_flow = linear_flow.Flow(detach_volume)
            volume_flow.add(volume_tasks.DetachVolume(
                cloud,
                name=detach_volume,
                provides=detach_volume,
                inject={"attachment": attachment},
            ))
        evacuate_volume = "evacuate-volume-{}".format(volume.id)
        evacuate_volume_host = "evacuate-volume-{}-host".format(volume.id)
        evacuate_flow = linear_flow.Flow(
            evacuate_volume,
            retry=retry.ForEach(
                values=hosts,
                provides=evacuate_volume_host,
            ),
        )
        volume_key = "volume-{}".format(volume.id)
        context.store[volume_key] = volume
        evacuate_flow.add(volume_tasks.EvacuateVolume(
            cloud,
            name=evacuate_volume,
            provides=evacuate_volume,
            rebind=[volume_key, evacuate_volume_host],
        ))
        if attachment:
            volume_flow.add(evacuate_flow)
            restore_attachment = "reattach-volume-{}".format(volume.id)
            volume_flow.add(volume_tasks.RestoreAttachment(
                cloud,
                name=restore_attachment,
                provides=restore_attachment,
                inject={"attachment": attachment},
            ))
            flow.add(volume_flow)
        else:
            flow.add(evacuate_flow)
    return flow


def evacuate_host(context, hostname):
    flow = linear_flow.Flow("evacuate-host-{}".format(hostname))
    flow.add(
        evacuate_servers(context, hostname),
        evacuate_volumes(context, hostname),
    )
    return flow
