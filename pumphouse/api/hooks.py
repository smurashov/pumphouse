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
        self.clouds = {}

    def set(self, name, service, client):
        self.clouds[name] = (service, client)

    def get(self, name):
        return self.clouds.get(name)


class Cloud(object):
    def __init__(self, target):
        self._reset_lock = gevent.lock.RLock()
        self.target = target

    def init_app(self, app):
        app.config.setdefault("CLOUDS", None)
        app.config.setdefault("CLOUD_DRIVER", "pumphouse.cloud.Cloud")
        app.config.setdefault("IDENTITY_DRIVER", "pumphouse.cloud.Identity")
        app.config.setdefault("CLOUD_SERVICE", "pumphouse.base.Service")
        app.config.setdefault("PARAMETERS", dict())

        clouds = self.register_extension(app)
        service = self.init_cloud_service(app)
        client = service.make()
        clouds.set(self.target, service, client)

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
        service = cloud_service(cloud_config,
                                self.target,
                                cloud_driver,
                                identity_driver)
        return service

    def reset(self, events):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            with self._reset_lock:
                clouds = self.get_extension(ctx.app)
                service, client = clouds.get(self.target)
                client = service.reset(events, client)
                clouds.set(self.target, service, client)

    def connect(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            clouds = self.get_extension(ctx.app)
            service, client = clouds.get(self.target)
            # TODO(akscram): One check is not enough.
            LOG.info("Trying to check client %s", client)
            if not service.check(client):
                LOG.warning("The client %s is unusable, try to reinitialize "
                            "it",
                            client)
                client = service.make(identity=client.identity)
                clouds.set(self.target, service, client)
            else:
                LOG.info("Client looks like alive %s", client)
            return client

    @property
    def cloud_urls(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            clouds = self.get_extension(ctx.app)
            service, client = clouds.get(self.target)
            return service.cloud_urls


source = Cloud("source")
destination = Cloud("destination")
