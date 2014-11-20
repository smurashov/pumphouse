# fuel-pumphouse
#
# Version     0.2

FROM debian:sid
MAINTAINER Andrew Woodward awoodward@mirantis.com

WORKDIR /root

ENV DEBIAN_FRONTEND noninteractive

# Note(xarses): https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=770157
RUN echo deb http://http.debian.net/debian testing main >> /etc/apt/sources.list && apt-get update && apt-get install -y --fix-missing -t testing python

# Install as many package requirements prior to letting pip chase them.
RUN apt-get update && \
  apt-get -y install --fix-missing git python-pip python-pexpect python-flake8 python-flask python-mccabe python-gevent-websocket python-keystoneclient python-novaclient python-glanceclient python-sqlalchemy python-flask python-taskflow python-six python-netaddr python-crypto python-gevent python-greenlet python-yaml python-six libpython2.7-stdlib=2.7.8-11

# Note(xarses): This is a hack to support bad /dev/{random,null,urandom,...}
#   support in docker versions prior to 1.0
RUN udevd -d && sleep 2 && udevadm control -e

ADD . /root/pumphouse

WORKDIR pumphouse

RUN pip -v install --allow-external mysql-connector-python /root/pumphouse