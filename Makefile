BUILDDIR = _build 
PACKAGEDIR = pumphouse
ifndef SERVER_NAME
  SERVER_NAME = 127.0.0.1:5000
endif
ifndef UI_URL
  UI_URL = ssh://pumphouse-ci-jenkins@gerrit.mirantis.com:29418/pumphouse/pumphouse-ui.git
endif

clean:
	find $(PACKAGEDIR) -name *.pyc -delete

api:
	if test -d ./pumphouse-ui; then \
		cd pumphouse-ui && git pull; \
	else \
		git clone $(UI_URL); \
	fi;
	test -d pumphouse/api/static || mkdir pumphouse/api/static
	cp -r pumphouse-ui/static/ajs pumphouse/api/static/
	cp pumphouse/api/static/ajs/index.html pumphouse/api/static/
	sed -i -e "s/SERVER_NAME: 127.0.0.1:5000/SERVER_NAME: $(SERVER_NAME)/" \
		doc/samples/api-config.yaml
	sed -i -e "s/localhost:3002/$(SERVER_NAME)/" \
		pumphouse/api/static/ajs/js/constants.js
