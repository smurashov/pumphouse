import logging

from . import management


LOG = logging.getLogger(__name__)


class Service(object):
    default_num_tenants = 2
    default_num_servers = 2

    def __init__(self, config, target, cloud_driver, identity_driver):
        self.identity_config = config.pop("identity")
        self.populate_config = config.pop("populate", None)
        self.workloads_config = config.pop("workloads", None)
        self.cloud_urls = config.pop("urls", None)
        self.cloud_config = config
        self.target = target
        self.cloud_driver = cloud_driver
        self.identity_driver = identity_driver

    def make(self, identity=None):
        if identity is None:
            identity = self.identity_driver(**self.identity_config)
        cloud = self.cloud_driver.from_dict(identity=identity,
                                            **self.cloud_config)
        LOG.info("Cloud client initialized for endpoint: %s",
                 self.cloud_config["endpoint"]["auth_url"])
        return cloud

    def check(self, cloud):
        return cloud.ping()

    def reset(self, events, cloud):
        management.cleanup(events, cloud, self.target)
        if isinstance(self.workloads_config, dict):
            management.setup(events, cloud, self.target,
                             workloads=self.workloads_config)
        elif isinstance(self.populate_config, dict):
            num_tenants = self.populate_config.get("num_tenants",
                                                   self.default_num_tenants)
            num_servers = self.populate_config.get("num_servers",
                                                   self.default_num_servers)
            management.setup(events, cloud, self.target, num_tenants,
                             num_servers)
        return cloud
