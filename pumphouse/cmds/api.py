# Copyright (c) 2014 Mirantis Inc.
#
# Licensed under the Apache License, Version 2.0 (the License);
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an AS IS BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and#
# limitations under the License.

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
