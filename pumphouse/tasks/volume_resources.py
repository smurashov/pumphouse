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

from pumphouse import exceptions
from pumphouse.tasks import volume as volume_tasks
from pumphouse.tasks import tenant as tenant_tasks
from pumphouse.tasks import user as user_tasks


LOG = logging.getLogger(__name__)


def migrate_volume(context, volume_id):
    volume = context.src_cloud.cinder.volumes.get(volume_id)
    volume_id = volume.id
    tenant_id = volume._info["os-vol-tenant-attr:tenant_id"]
    tenant_retrieve = "tenant-{}-retrieve".format(tenant_id)
    import pdb; pdb.set_trace()
    try:
        users = context.src_cloud.keystone.tenants.list_users(
            tenant_id)
    except exceptions.keystone_excs.NotFound:
        LOG.info("No users in tenant %s, using %s",
                 tenant_id,
                 context.dst_cloud.keystone.auth_ref["user"]["name"])
        user_id = None
    else:
        user = users.pop()
        if str(user.name) == "admin":
            user_id = None
        else:
            user_id = user.id
    user_retrieve = "user-{}-retrieve".format(user_id)
    resources = []

    if tenant_retrieve not in context.store:
        tenant_flow = tenant_tasks.migrate_tenant(context,
                                                  tenant_id)
    if user_id and user_retrieve not in context.store:
        user_flow = user_tasks.migrate_user(context,
                                            user_id)
    resources.append(tenant_flow)
    volume_flow = volume_tasks.migrate_detached_volume(context,
                                                       volume_id,
                                                       user_id,
                                                       tenant_id)
    return resources, volume_flow
