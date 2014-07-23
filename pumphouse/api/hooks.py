import gevent.lock
import logging

import flask
from flask.ext import socketio

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
        service = cloud_service(cloud_config, self.target, cloud_driver, identity_driver)
        return service

    def reset(self, events):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            with self._reset_lock:
                clouds = self.get_extension(ctx.app)
                service, client = clouds.get(self.target)
                client = service.reset(events, client)
                clouds.set(self.target, service, client)

    @property
    def client(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            clouds = self.get_extension(ctx.app)
            service, client = clouds.get(self.target)
            # TODO(akscram): One check is not enough.
            if not service.check(client):
                client = service.make()
                clouds.set(self.target, service, client)
            return client


events = socketio.SocketIO()
source = Cloud("source")
destination = Cloud("destination")
