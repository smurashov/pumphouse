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


class Registry(object):
    """Registry of plugins."""

    def __init__(self):
        self.plugins = {}

    def register(self, target):
        """Register a plugin by the target.

        :param target: a string with name of the plugin
        :returns: an instance of :class:`Plugin`
        :raises: :class:`exceptions.PluginAlreadyRegisterError`
                    if the plugin with the given target already
                    registered.
        """
        if target in self.plugins:
            raise exceptions.PluginAlreadyRegisterError(target=target)
        self.plugins[target] = plugin = Plugin(target)
        return plugin

    def get(self, target):
        """Get the plugin by the target.

        :param target: a string with name of the plugin
        :returns: an instance of :class:`Plugin`
        :raises: :class:`exceptions.PluginAlreadyRegisterError`
                    if the plugin with the given target already
                    registered.
        """
        if target not in self.plugins:
            raise exceptions.PluginNotFoundError(target=target)
        return self.plugins[target]

    def __iter__(self):
        return iter(self.plugins)


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
        self.implementations = {}

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
            self.implementations[name] = func
            return func

        if name in self.implementations:
            raise exceptions.FuncAlreadyRegisterError(target=self.target,
                                                      name=name)
        return decorate

    def select(self, name):
        if name not in self.implementations:
            raise exceptions.FuncNotFoundError(target=self.target,
                                               name=name)
        return self.implementations[name]

    def select_from_config(self, config, default=None):
        switch = config.get(self.target, default)
        return self.select(switch)

    def __iter__(self):
        return iter(self.implementations)
