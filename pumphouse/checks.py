import subprocess
import signal
from pumphouse import exceptions

CHECK_TIMELIMIT=7

class PumpHouseCheck(object):
    config = None

    def __init__(self, config):
        self.config = config

    def run():
        raise NotImplementedError()

def alarm_handler(signum, frame):
  raise exceptions.CheckTimeout() 

class PumpHouseShellCheck(PumpHouseCheck):
    def __init__(self, config):
        try:
            if not(isinstance(config, dict) and
                   isinstance(config['input'], list) and
                   isinstance(config['env'], dict) and
                   isinstance(config['cmd'], str)):
                raise exceptions.UsageError()
            super(PumpHouseShellCheck, self).__init__(config)
        except KeyError:
            raise exceptions.ConfigError()

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
        command = ("xargs -r -I% -P16 sh -c \"({} {})"
                   " >/dev/null 2>&1 || (echo %; exit 255)\" 2>/dev/null"
                   .format(environment, self.config['cmd']))
        try:
          proc = subprocess.Popen(command,
                                shell=True,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
          raise exceptions.CheckRunError() 

        signal.signal(signal.SIGALRM, alarm_handler)
        signal.alarm(CHECK_TIMELIMIT)
        try:
          r = proc.communicate(inputStream)[0].rstrip().split("\n")
          signal.alarm(0) 
        except exceptions.CheckTimeout:
          raise 
          
        if (r[0]):
            raise exceptions.CheckError(r)

        return 1
