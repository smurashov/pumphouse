import logging

import flask

from . import handlers
from . import hooks


def create_app():
    """Creates a WSGI application.

    Configuration of the application initialized with default extra
    values. Registered the Pumphouse blueprints.

    :returns: a :class:`flask.Fask` instance
    """
    app = flask.Flask(__name__)
    app.register_blueprint(handlers.pump)
    app.config.update({
        "CLOUDS": None,
        "CLOUD_DRIVER": "pumphouse.cloud.Cloud",
        "IDENTITY_DRIVER": "pumphouse.cloud.Identity",
    })
    return app


def start_app(config=None, **kwargs):
    """Starts the created application with given configuration.

    :param config: a dict with configuration values
    """
    logging.basicConfig(level=logging.INFO)
    app = create_app()
    if config is not None:
        app.config.update(config)
    hooks.events.init_app(app)
    hooks.events.run(app)


if __name__ == "__main__":
    start_app()
