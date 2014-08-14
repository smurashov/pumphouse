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

from keystoneclient.openstack.common.apiclient import (exceptions  # NOQA
                                                       as keystone_excs)  # NOQA
from novaclient import exceptions as nova_excs  # NOQA
from glanceclient import exc as glance_excs  # NOQA


class Error(Exception):
    pass


class NotFound(Error):
    pass


class HostNotInSourceCloud(Error):
    pass


class TimeoutException(Error):
    pass
