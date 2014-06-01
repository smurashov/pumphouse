import argparse
import yaml


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
    return parser


def read_configuration(stream):
    with stream as f:
        return yaml.safe_load(f.read())


def main():
    parser = get_parser()
    args = parser.parse_args()

# TODO(akscram): The first stage is a discovering of clouds.
#    source = discovery(args.config["source"]["endpoint"])
#    destination = discovery(args.config["destination"]["endpoint"])


if __name__ == "__main__":
    main()
