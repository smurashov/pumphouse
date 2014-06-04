#!/usr/bin/python
import argparse
import os
import sys

sys.path.append('../')

import pumphouse
from pumphouse import cmd
from pumphouse import cloud

def main():
    parser = cmd.get_parser()
    args = parser.parse_args()

# TODO(akscram): The first stage is a discovering of clouds.
    source = cloud.Cloud(args.config["source"]["endpoint"])
#    destination = cloud.Cloud(args.config["destination"]["endpoint"])

    resource = source.discover(args.resource_class, args.resource_id)
#    destination.migrate(args.resource)
    print resource.name

if __name__ == "__main__":
    main()
