import flask


pump = flask.Blueprint("pumphouse", __name__)


@pump.route("/resources")
def resources():
    return "resources"


@pump.route("/events")
def events():
    return "events"
