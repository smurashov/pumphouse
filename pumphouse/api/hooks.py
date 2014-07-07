import logging

import flask
from flask.ext import socketio
from werkzeug.local import LocalProxy

from pumphouse import utils


LOG = logging.getLogger(__name__)

events = socketio.SocketIO()


def setup_cloud(cloud_name):
    """Initializes the decorator for creating connection to a cloud.

    :param cloud_name: a string with the name of the initialized cloud
    :returns: a callback that create a real connection
    """
    attribute_name = "{}_cloud".format(cloud_name)
    def setup_selected_cloud():
        cloud = getattr(flask.g, attribute_name, None)
        if cloud is None:
            config = flask.current_app.config
            cloud_config = config["CLOUDS"][cloud_name]

            LOG.debug("Cloud driver will be used: %s", config["CLOUD_DRIVER"])
            Cloud = utils.load_class(config["CLOUD_DRIVER"])
            LOG.debug("Identity driver will be used: %s", config["IDENTITY_DRIVER"])
            Identity = utils.load_class(config["IDENTITY_DRIVER"])

            identity = Identity(**cloud_config["identity"])
            cloud = Cloud.from_dict(endpoint=cloud_config["endpoint"],
                                    identity=identity)
            LOG.info("Cloud client initialized for endpoint: %s",
                     cloud_config["endpoint"]["auth_url"])
            setattr(flask.g, attribute_name, cloud)
        return cloud
    return setup_selected_cloud


source = LocalProxy(setup_cloud("source"))
destination = LocalProxy(setup_cloud("destination"))
