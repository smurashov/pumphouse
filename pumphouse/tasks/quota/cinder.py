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

from pumphouse.tasks.quota import base


LOG = logging.getLogger(__name__)


class CinderClientMixin(object):
    def __init__(self, *args, **kwargs):
        super(CinderClientMixin, self).__init__(*args, **kwargs)
        self.client = self.cloud.cinder


class RetrieveTenantQuota(CinderClientMixin, base.RetrieveTenantQuota):
    pass


class RetrieveDefaultQuota(CinderClientMixin, base.RetrieveDefaultQuota):
    pass


class EnsureTenantQuota(CinderClientMixin, base.EnsureTenantQuota):
    pass


class EnsureDefaultQuota(CinderClientMixin, base.EnsureTenantQuota):
    pass
