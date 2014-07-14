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
            LOG.info("Identity driver will be used: %s",
                     config["IDENTITY_DRIVER"])
            identity_driver = utils.load_class(config["IDENTITY_DRIVER"])
            LOG.info("Cloud driver will be used: %s", config["CLOUD_DRIVER"])
            cloud_driver = utils.load_class(config["CLOUD_DRIVER"])
            LOG.info("Cloud initializer will be used: %s",
                     config["CLIENT_MAKER"])
            make_client = utils.load_class(config["CLIENT_MAKER"])
            cloud_config = config["CLOUDS"][cloud_name]
            cloud = make_client(cloud_config, cloud_name, cloud_driver,
                                identity_driver)
            setattr(flask.g, attribute_name, cloud)
        return cloud
    return setup_selected_cloud


source = LocalProxy(setup_cloud("source"))
destination = LocalProxy(setup_cloud("destination"))
