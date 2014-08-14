#import exceptions
import subprocess
from . import exceptions

class PumpHouseCheck(object):
    config = None

    def __init__(self, config):
        self.config = config

    def run():
        raise NotImplementedError()

class PumpHouseShellCheck(PumpHouseCheck):


    def __init__(self, config):
        try:
            if not(isinstance(config, dict) and
                isinstance(config['input'], list) and
                isinstance(config['env'], dict) and
                isinstance(config['cmd'], str)):
                    raise exceptions.UsageError()


            super(PumpHouseShellCheck, self).__init__(config);


        except KeyError:
            raise exceptions.ConfigError();


    def generateEnv(self, env):
        r = ""
        for key in env:
            r = r + key + "=\'" + str(env[key]) + "\'; "
        return r

    def generateInputStream(self, inputData):
        return "\n".join(inputData) + '\n'

    def run(self):
        inputStream = self.generateInputStream(self.config['input'])
        environment = self.generateEnv(self.config['env'])

        command = "xargs -I^ -P16 sh -c \"%s %s >/dev/null 2>&1 || (echo ^; exit 255)\" 2>/dev/null" % (environment, self.config['cmd'])


        proc = subprocess.Popen(command, shell=True , stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        return proc.communicate(inputStream)[0].rstrip().split("\n");
