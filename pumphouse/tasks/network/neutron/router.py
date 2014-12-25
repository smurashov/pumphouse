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

import inspect
import logging

from pumphouse import task
from taskflow.patterns import graph_flow

from . import utils

LOG = logging.getLogger(__name__)


def get_router_by(neutron, router_filter):
    try:
        return neutron.list_routers(**router_filter)['routers']
    except Exception as e:
        raise e


class RetrieveAllRouters(task.BaseCloudTask):

    def execute(self):
        return get_router_by(self.cloud.neutron, {})


class RetrieveRouterById(task.BaseCloudTask):

    def execute(self, all_routers, router_id):
        for router in all_routers:
            if (router['id'] == router_id):
                return router

        return None


class EnsureRouter(task.BaseCloudTask):

    def execute(self, all_routers, router_info):
        for router in all_routers:
            if (router["name"] == router_info["name"]):
                return router

        del router_info['id']

        router = self.cloud.neutron.create_router(
            {'router': router_info}
        )['router']
        return router


def migrate_router(context, router_id):

    router_binding = router_id

    (router_retrieve, router_ensure) = utils.generate_binding(
        router_binding, inspect.stack()[0][3])

    if (router_binding in context.store):
        return None, router_ensure

    context.store[router_binding] = router_id

    f = graph_flow.Flow("neutron-router-migration-{}".format(router_id))

    all_src_router_binding = "srcNeutronAllRouters"
    all_dst_router_binding = "dstNeutronAllRouters"

    if (all_src_router_binding not in context.store):

        f.add(RetrieveAllRouters(
            context.src_cloud,
            name="retrieveAllSrcRouters",
            provides=all_src_router_binding
        ))

        context.store[all_src_router_binding] = None

    if (all_dst_router_binding not in context.store):

        f.add(RetrieveAllRouters(
            context.dst_cloud,
            name="retrieveAllDstRouters",
            provides=all_dst_router_binding
        ))

        context.store[all_dst_router_binding] = None

    f.add(RetrieveRouterById(context.src_cloud,
                             name=router_retrieve,
                             provides=router_retrieve,
                             rebind=[
                                 all_src_router_binding,
                                 router_binding
                             ]))

    f.add(EnsureRouter(context.dst_cloud,
                       name=router_ensure,
                       provides=router_ensure,
                       rebind=[
                           all_dst_router_binding,
                           router_retrieve
                       ]))

    return f, router_ensure
