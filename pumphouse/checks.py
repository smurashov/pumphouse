#import exceptions
from . import exceptions

class PumpHouseCheck(object):
    config = None

    def __init__(self, config):
        self.config = config

    def run():
        raise NotImplemented()

class PumpHouseShellCheck(PumpHouseCheck):


    def __init__(self, config):
        try:
            if (type(config) is not dict or
                type(config['input']) is not list or
                type(config['env']) is not dict or
                type(config['cmd']) is not str):
                raise exceptions.UsageError()


            super(PumpHouseShellCheck, self).__init__(config);


        except KeyError:
            raise exceptions.ConfigError();


    def createEnv(self, env):
        r = ""
        for key in env:
            r = r + key + "=\'" + str(env[key]) + "\' "
        return r

    def run(self):
        inputStream = "\n".join(self.config['input']) + '\n'
        environment = self.createEnv(self.config['env'])

