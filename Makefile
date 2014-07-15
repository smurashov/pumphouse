BUILDDIR = _build 
PACKAGEDIR = pumphouse
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
	cp -r pumphouse-ui/static/ajs pumphouse/api/static/
	cp pumphouse/api/static/ajs/index.html pumphouse/api/static/
