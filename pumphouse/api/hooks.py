import logging

import flask
from flask.ext import socketio

from pumphouse import utils


LOG = logging.getLogger(__name__)


class Clouds(object):
    def __init__(self):
        self.clouds = {}

    def set(self, name, client):
        self.clouds[name] = client

    def get(self, name):
        return self.clouds.get(name)


class Cloud(object):
    def __init__(self, target):
        self.target = target
        self._client = None

    def init_app(self, app):
        app.config.setdefault("CLOUDS", None)
        app.config.setdefault("CLOUD_DRIVER", "pumphouse.cloud.Cloud")
        app.config.setdefault("IDENTITY_DRIVER", "pumphouse.cloud.Identity")
        app.config.setdefault("CLIENT_MAKER", "pumphouse.cloud.make_client")

        clouds = self.register_extension(app)
        client = self.make_client(app)
        clouds.set(self.target, client)

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

    def make_client(self, app):
        config = app.config
        LOG.info("Identity driver will be used: %s",
                 config["IDENTITY_DRIVER"])
        identity_driver = utils.load_class(config["IDENTITY_DRIVER"])
        LOG.info("Cloud driver will be used: %s", config["CLOUD_DRIVER"])
        cloud_driver = utils.load_class(config["CLOUD_DRIVER"])
        LOG.info("Cloud initializer will be used: %s",
                 config["CLIENT_MAKER"])
        make_client = utils.load_class(config["CLIENT_MAKER"])
        cloud_config = config["CLOUDS"][self.target].copy()
        cloud = make_client(cloud_config, self.target, cloud_driver,
                            identity_driver)
        return cloud

    def reset(self):
        app = flask.current_app
        clouds = self.register_extension(app)
        client = self.make_client(app)
        clouds.set(self.target, client)

    @property
    def client(self):
        ctx = flask._app_ctx_stack.top
        if ctx is not None:
            return self.get_extension(ctx.app).get(self.target)


events = socketio.SocketIO()
source = Cloud("source")
destination = Cloud("destination")
