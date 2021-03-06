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

PREFIX = "neutron-"


def generate_binding(uid, label):
    label.replace("_", "-")
    return PREFIX + "{}-{}-ensure".format(label, uid), \
        PREFIX + "{}-{}-retrieve".format(label, uid)


def generate_retrieve_binding(prefix):
    return prefix + "-src", prefix + "-dst", \
        prefix + "-src-retrieve", prefix + "-dst-retrieve"
