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
EXTRA_TARGETS = reply.txt faq.html default.css

include scripts/make.rules
ROOT_DIR = .
ROOT_OFFSET = .

VERSION_PY = $(shell python -c 'import os;\
from spambayes import Version;\
f = Version.__file__;\
print os.path.splitext(f)[0]+".py";\
')

$(TARGETS): links.h

# hackery to whack the faq into ht2html...

DUHTML = html.py
faq.ht : faq.txt
	$(DUHTML) faq.txt > faq.body.tmp
	echo "Title: SpamBayes FAQ" > faq.ht
	echo "Author-Email: SpamBayes@python.org" >> faq.ht
	echo "Author: SpamBayes" >> faq.ht
	echo "" >> faq.ht
	cat faq.body.tmp | sed -e '1,/<body>/d' -e '/<\/body>/,$$d' >> faq.ht
	rm faq.body.tmp

faq.html : faq.ht
	./scripts/ht2html/ht2html.py -f -s SpamBayesFAQGenerator -r . ./faq.ht

version: download/Version.cfg

download/Version.cfg: $(VERSION_PY)
	python $(VERSION_PY) -g > download/Version.cfg.tmp
	rsync --rsh=$(RSYNC_RSH) -v -r -l -t $(LOCAL_INCLUDE)  ./download/Version.cfg.tmp $(LIVE_DEST)/download/Version.cfg
	mv -f download/Version.cfg.tmp download/Version.cfg

local_install: 
	cd download ; $(MAKE) install

