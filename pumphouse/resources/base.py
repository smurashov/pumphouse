class Discovery(object):
    def __init__(self, config):
        self.username = config['username']
        self.password = config['password']
        self.auth_url = config['auth_url']
        self.tenant = config['tenant']
