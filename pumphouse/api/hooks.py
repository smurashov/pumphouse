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

import gevent.lock
import logging

import flask

from pumphouse import utils


LOG = logging.getLogger(__name__)


class Clouds(object):
    def __init__(self):
        self._services = {}
        self._clients = {}

    def register(self, name, service):
        self._services[name] = service

    def connect(self, name):
        service = self._services[name]
        client = self._clients.get(name)
        if client is None:
            client = service.make()
            self._clients[name] = client
        else:
            LOG.debug("Trying to check client %s", client)
            if not service.check(client):
                LOG.warning("The client %s is broken, try to get yet one",
                            client)
                # TODO(akscram): One try is not enough.
                client = service.make(identity=client.identity)
                self._clients[name] = client
        return service, client


class Cloud(object):
    def __init__(self, target):
        self._reset_lock = gevent.lock.RLock()
        self.target = target

    def init_app(self, app):
        app.config.setdefault("CLOUDS", None)
        app.config.setdefault("CLOUD_DRIVER", "pumphouse.cloud.Cloud")
        app.config.setdefault("IDENTITY_DRIVER", "pumphouse.cloud.Identity")
        app.config.setdefault("CLOUD_SERVICE", "pumphouse.base.Service")
        clouds = self.register_extension(app)
        service = self.init_cloud_service(app)
        clouds.register(self.target, service)

    def register_extension(self, app):
        if not hasattr(app, "extensions"):
            app.extensions = {}
        if "clouds" not in app.extensions:
            app.extensions["clouds"] = clouds = Clouds()
        else:
            clouds = app.extensions["clouds"]
        return clouds

    def get_extension(self, app):
        return app.extensions["clouds"]

    def init_cloud_service(self, app):
        config = app.config
        LOG.info("Identity driver will be used: %s",
                 config["IDENTITY_DRIVER"])
        identity_driver = utils.load_class(config["IDENTITY_DRIVER"])
        LOG.info("Cloud driver will be used: %s", config["CLOUD_DRIVER"])
        cloud_driver = utils.load_class(config["CLOUD_DRIVER"])
        LOG.info("Cloud initializer will be used: %s",
                 config["CLOUD_SERVICE"])
        cloud_config = config["CLOUDS"][self.target].copy()
        cloud_service = utils.load_class(config["CLOUD_SERVICE"])
        plugins = config.get("PLUGINS", {})
        service = cloud_service(cloud_config,
                                plugins,
                                self.target,
                                cloud_driver,
                                identity_driver)
        return service

    def reset(self, events):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            with self._reset_lock:
                clouds = self.get_extension(ctx.app)
                service, client = clouds.connect(self.target)
                service.reset(events, client)

    def connect(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            clouds = self.get_extension(ctx.app)
            _, client = clouds.connect(self.target)
            return client

    def config(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            clouds = self.get_extension(ctx.app)
            service, _ = clouds.connect(self.target)
            return service.cloud_config

    @property
    def cloud_urls(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            clouds = self.get_extension(ctx.app)
            service, _ = clouds.connect(self.target)
            return service.cloud_urls


source = Cloud("source")
destination = Cloud("destination")
