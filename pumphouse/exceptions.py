class Error(Exception):
    pass


class NotFound(Error):
    pass


class HostNotInSourceCloud(Error):
    pass


class TimeoutException(Error):
    pass