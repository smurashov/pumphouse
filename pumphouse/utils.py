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

import itertools
import logging
import logging.config
import operator
import string
import sys
import time
import traceback
import yaml
import re
from collections import defaultdict

from requests import exceptions as req_excs

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
             attribute_getter=status_attr, value=None, error_value=None,
             timeout=60, check_interval=1, expect_excs=None, stop_excs=None):
    if expect_excs:
        expect_excs = tuple(expect_excs) + (req_excs.ConnectionError,)
    else:
        expect_excs = (req_excs.ConnectionError,)
    if stop_excs is None:
        if value is None:
            value = "ACTIVE"
        if error_value is None:
            error_value = "ERROR"
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

chain = lambda g: (e for i in g for e in i)
_tuples = (itertools.combinations_with_replacement(string.uppercase, l)
           for l in itertools.count(1))
counter = itertools.imap(''.join, chain(_tuples))
ids = defaultdict(lambda: next(counter))
id_re = re.compile(r"""
    [0-9a-fA-F]{8}(-?)(?:[0-9a-fA-F]{4}\1){3}[0-9a-fA-F]{12}  # UUID
    |                                                         # or
    pumphouse-(?:-[a-zA-Z]+)?(?:-\d+)?                        # synthetic name
""", re.VERBOSE)


def eat_ids(s):
    return id_re.sub(lambda match: ids[match.group(0)], s)


def dump_flow(flow, f, first=False, prev=None):
    import taskflow.flow
    import taskflow.patterns.linear_flow
    linear = isinstance(flow, taskflow.patterns.linear_flow.Flow)
    if first:
        f.write('digraph "%s" {\n'
                'graph[rankdir=LR]\nnode[shape=box]\n'
                'edge[style=dashed]' % (eat_ids(flow.name),))
    else:
        f.write('subgraph "cluster_%s" {\n'
                'graph[style=%s,rankdir=LR]\n' % (
                    eat_ids(flow.name),
                    'dashed' if linear else 'dotted'))
    last = None
    for item in flow:
        if isinstance(item, taskflow.flow.Flow):
            last = dump_flow(item, f, prev=prev)
        else:
            last = dump_task(item, f, prev=prev)
        if linear:
            prev = last
        else:
            prev = None
    f.write('}\n')
    return last


def dump_task(task, f, prev=None):
    for r in task.requires:
        if not prev or prev.name != r:
            f.write('"%s" -> "%s"\n' % (eat_ids(r), eat_ids(task.name)))
    if prev:
        f.write('"%s" -> "%s" [style=bold]\n' % (eat_ids(prev.name),
                                                 eat_ids(task.name)))
    return task


def configure_logging(config):
    log_config = config.get("LOGGING")
    if log_config is None:
        logging.basicConfig(level=logging.DEBUG)
    else:
        log_config.update(version=1, disable_existing_loggers=False)
        logging.config.dictConfig(log_config)
