import flask

from . import handlers


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
    print(app.config.root_path)
    return app


def start_app(config=None, **kwargs):
    """Starts the created application with given configuration.

    :param config: a dict with configuration values
    """
    app = create_app()
    if config is not None:
        app.config.update(config)
    app.run(**kwargs)


if __name__ == "__main__":
    start_app()
