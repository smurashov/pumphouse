import argparse

from pumphouse.api import app
from pumphouse import utils


def get_parser():
    parser = argparse.ArgumentParser(description="API for resources migration "
                                                 "utility through OpenStack "
                                                 "clouds.")
    parser.add_argument("config",
                        type=utils.safe_load_yaml,
                        nargs="?",
                        help="A filename of a configuration for application")
    return parser


def main():
    args = get_parser().parse_args()
    app.start_app(args.config)
