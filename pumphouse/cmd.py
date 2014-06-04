import argparse
import yaml
from pumphouse import cloud
from pumphouse.services import base
from pumphouse.resources import base


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f.read())


def get_parser():
    parser = argparse.ArgumentParser(description="Migration resources through "
                                                 "OpenStack clouds.")
    parser.add_argument("config",
                        type=safe_load_yaml,
                        help="Configuration of cloud endpoints and a "
                             "strategy.")
    parser.add_argument("resource_class",
                        help="Class name of resource to migrate")
    parser.add_argument("resource_id",
                        help="ID of migrating resourcre")
    return parser


def read_configuration(stream):
    with stream as f:
        return yaml.safe_load(f.read())


def main():
    parser = get_parser()
    args = parser.parse_args()

# TODO(akscram): The first stage is a discovering of clouds.
    source = cloud.Cloud(args.config["source"]["endpoint"])
    destination = cloud.Cloud(args.config["destination"]["endpoint"])

    resource = source.discover(args.resource_class, args.resource_id)
#    destination.migrate(args.resource)
    print resource

if __name__ == "__main__":
    main()
