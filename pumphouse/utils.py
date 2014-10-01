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

import logging
import operator
import sys
import time
import traceback
import yaml

from . import exceptions


LOG = logging.getLogger(__name__)


def safe_load_yaml(filename):
    with open(filename) as f:
        return yaml.safe_load(f)


def load_class(import_path):
    mod_str, _sep, class_str = import_path.rpartition('.')
    try:
        __import__(mod_str)
        return getattr(sys.modules[mod_str], class_str)
    except (ValueError, AttributeError):
        raise ImportError('Class %s cannot be found (%s)' %
                          (class_str,
                           traceback.format_exception(*sys.exc_info())))


status_attr = operator.attrgetter("status")


def wait_for(resource, update_resource,
             attribute_getter=status_attr, value="ACTIVE", error_value="ERROR",
             timeout=60, check_interval=1, expect_excs=None, stop_excs=None):
    start = time.time()
    while True:
        LOG.debug("Trying to get resource: %s", resource)
        try:
            upd_resource = update_resource(resource)
        except stop_excs:
            LOG.exception("Could not fetch updated resource: %s", resource)
            break
        except expect_excs as exc:
            LOG.warn("Expected exception: %s", exc.message)
        else:
            LOG.debug("Got resource: %s", upd_resource)
            result = attribute_getter(upd_resource)
            if result == value:
                return upd_resource
            if result == error_value:
                raise exceptions.Error(
                    "Resource %s fell into error state" % resource)
        time.sleep(check_interval)
        if time.time() - start > timeout:
            raise exceptions.TimeoutException()
