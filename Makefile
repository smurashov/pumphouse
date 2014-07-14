BUILDDIR = _build 
PACKAGEDIR = pumphouse

.PHONY: clean api

clean:
	find $(PACKAGEDIR) -name *.pyc -delete

api:
	git clone ssh://gerrit.mirantis.com:29418/pumphouse/pumphouse-ui
	cp -r pumphouse-ui/static/ajs pumphouse/api/static/
	cp pumphouse/api/static/ajs/index.html pumphouse/api/static/
