# Makefile for the SpamBayes website.
#
# targets supported:
# (default): generate all .html content locally.  This includes the
#            FAQ (.txt->.ht->.html) and the rest (.ht->.html)
# install: rsync the locally generated content (excluding Version.cfg)
# version: generate download/Version.cfg, and rsync to the website.
#          Ensure you have *installed* (not just 'cvs up'd) the latest 
#          SpamBayes CVS before making this target.

# this def'n must occur before the include!
EXTRA_TARGETS = reply.txt faq.html default.css subdirs

include scripts/make.rules
ROOT_DIR = .
ROOT_OFFSET = .

VERSION_PY = $(shell python -c 'import os;\
from spambayes import Version;\
f = Version.__file__;\
print (os.path.splitext(f)[0]+".py").replace("\\", "/");\
')

$(shell python scripts/create_experimental_pages.py)

$(TARGETS): links.h

FAQ_TITLE=SpamBayes FAQ

version: download/Version.cfg

download/Version.cfg: $(VERSION_PY)
	python $(VERSION_PY) -g > download/Version.cfg.tmp
	rsync --rsh=$(RSYNC_RSH) -v -r -l -t $(LOCAL_INCLUDE)  ./download/Version.cfg.tmp $(LIVE_DEST)/download/Version.cfg
	mv -f download/Version.cfg.tmp download/Version.cfg

# Not sure what the correct magic for subdirs is
# want 'make' to recurse without 'install' and
# 'make install' to recurse *with* 'install'
local_install:
	-cd apps; $(MAKE) install
	-cd download ; $(MAKE) install
	-cd sigs; $(MAKE) install

subdirs:
	cd apps; $(MAKE) 
	cd download ; $(MAKE)
	cd sigs ; $(MAKE)

