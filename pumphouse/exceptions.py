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
# from neutronclient.common import exceptions as neutron_excs  # NOQA
from glanceclient import exc as glance_excs  # NOQA
from cinderclient import exceptions as cinder_excs  # NOQA


class Error(Exception):
    pass


class PluginError(Error):
    def __init__(self, target, *args, **kwargs):
        super(PluginError, self).__init__(*args, **kwargs)
        self.target = target


class PluginAlreadyRegisterError(PluginError):
    pass


class PluginNotFoundError(PluginError):
    pass


class PluginFuncError(PluginError):
    def __init__(self, target, name, *args, **kwargs):
        super(PluginFuncError, self).__init__(target, *args, **kwargs)
        self.name = name


class FuncNotFoundError(PluginFuncError):
    pass


class FuncAlreadyRegisterError(PluginFuncError):
    pass


class NotFound(Error):
    pass


class HostNotInSourceCloud(Error):
    pass


class TimeoutException(Error):
    pass


class Conflict(Error):
    pass


class ConfigError(Error):
    pass


class UsageError(Error):
    pass


class CheckError(Error):
    def __init__(self, failList):
        self.failList = failList


class CheckRunError(Error):
    pass


class CheckTimeout(Error):
    pass
