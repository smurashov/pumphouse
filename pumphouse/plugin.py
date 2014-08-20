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

from pumphouse import exceptions


class Plugin(object):
    """Represents plugabble functions.

    Allow to add different implementations of functions with the same
    interface and then choosing one from them.

    :param target: a name of the plugin
    """
    # TODO(akscram): A list of requirements is necessary to inspect
    #                implementations.
    def __init__(self, target):
        self.target = target
        self.implements = {}

    def add(self, name):
        """Register a function.

        This method returns the decorator which registers a function.

        :param name: a string with the name of registered function
        :returns: a decorator
        :raises: :class:`exceptions.FuncAlreadyRegisterError`
                    if the name already registered
        """
        def decorate(func):
            # TODO(akscram): The func should be inspected here by number of
            #                argument.
            self.implements[name] = func
            return func

        if name in self.implements:
            raise exceptions.FuncAlreadyRegisterError(target=self.target,
                                                      name=name)
        return decorate

    def select(self, name):
        if name not in self.implements:
            raise exceptions.FuncNotFoundError(target=self.target,
                                               name=name)
        return self.implements[name]
