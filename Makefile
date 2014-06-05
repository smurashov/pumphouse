BUILDDIR = _build 
PACKAGEDIR = pumphouse

.PHONY: clean

clean:
	find $(PACKAGEDIR) -name *.pyc -delete
