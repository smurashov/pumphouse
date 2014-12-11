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

import flask

from . import handlers
from . import hooks

from pumphouse import events
from pumphouse import utils


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
        bind_host = app.config.get("BIND_HOST", app.config["SERVER_NAME"])
        if bind_host is not None:
            host, _, port = bind_host.partition(":")
            if isinstance(port, basestring) and port.isdigit():
                port = int(port)
            else:
                port = None
            return (host, port)
        return (None, None)

    utils.configure_logging(config)
    app = create_app()
    app.config.setdefault("CLOUDS_RESET", False)
    app.config.setdefault("BIND_HOST", None)
    app.config.setdefault("PLUGINS", None)
    if config is not None:
        app.config.update(config)
    events.init_app(app)
    hooks.source.init_app(app)
    hooks.destination.init_app(app)
    host, port = get_bind_host()
    events.run(app, policy_server=False, host=host, port=port)


if __name__ == "__main__":
    start_app()
