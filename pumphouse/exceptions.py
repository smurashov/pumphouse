class Error(Exception):
    pass


class NotFound(Error):
    pass


class HostNotInSourceCloud(Error):
    pass


class TimeoutException(Error):
    pass

class ConfigError(Error):
    pass

class UsageError(Error):
    pass

class CheckError(Error):
    def __init__(self, failList):
        self.failList = failList

