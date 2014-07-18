import logging

import flask

from . import handlers
from . import hooks


def create_app():
    """Creates a WSGI application.

    Registers all blueprints for created application.

    :returns: a :class:`flask.Fask` instance
    """
    app = flask.Flask(__name__)
    app.register_blueprint(handlers.pump)
    return app


def start_app(config=None, **kwargs):
    """Starts the created application with given configuration.

    :param config: a dict with configuration values
    """
    def get_bind_host():
        bind_host = app.config["BIND_HOST"]
        if bind_host is None:
            server_name = app.config["SERVER_NAME"]
            if server_name is not None:
                bind_host, _, _ = server_name.partition(":")
        return bind_host

    logging.basicConfig(level=logging.INFO)
    app = create_app()
    app.config.setdefault("BIND_HOST", None)
    if config is not None:
        app.config.update(config)
    hooks.events.init_app(app)
    hooks.source.init_app(app)
    hooks.destination.init_app(app)
    hooks.events.run(app, host=get_bind_host(), policy_server = False)


if __name__ == "__main__":
    start_app()
