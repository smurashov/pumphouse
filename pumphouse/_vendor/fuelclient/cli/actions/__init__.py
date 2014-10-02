#    Copyright 2014 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""fuelclient.cli.actions sub-module contains files with action classes
which implement command line interface logic

All action classes must be added to action_tuple to be used by parser
"""
from .deploy import DeployChangesAction
from .environment import EnvironmentAction
from .fact import DeploymentAction
from .fact import ProvisioningAction
from .health import HealthCheckAction
from .interrupt import ResetAction
from .interrupt import StopAction
from .network import NetworkAction
from .node import NodeAction
from .release import ReleaseAction
from .role import RoleAction
from .settings import SettingsAction
from .snapshot import SnapshotAction
from .task import TaskAction
from .user import UserAction

actions_tuple = (
    ReleaseAction,
    RoleAction,
    EnvironmentAction,
    DeployChangesAction,
    NodeAction,
    DeploymentAction,
    ProvisioningAction,
    StopAction,
    ResetAction,
    SettingsAction,
    NetworkAction,
    TaskAction,
    SnapshotAction,
    HealthCheckAction,
    UserAction
)

actions = dict(
    (action.action_name, action())
    for action in actions_tuple
)
