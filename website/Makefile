# this def'n must occur before the include!
EXTRA_TARGETS = reply.txt faq.html default.css download/Version.cfg

include scripts/make.rules
ROOT_DIR = .
ROOT_OFFSET = .	

$(TARGETS): links.h

# hackery to whack the faq into ht2html...

DUHTML = html.py
faq.ht : faq.txt
	echo "Title: SpamBayes FAQ" > faq.ht
	echo "Author-Email: SpamBayes@python.org" >> faq.ht
	echo "Author: SpamBayes" >> faq.ht
	echo "" >> faq.ht
	$(DUHTML) faq.txt | sed -e '1,/<body>/d' -e '/<\/body>/,$$d' >> faq.ht

faq.html : faq.ht
	./scripts/ht2html/ht2html.py -f -s SpamBayesFAQGenerator -r . ./faq.ht

download/Version.cfg: ../spambayes/Version.py
	../spambayes/Version.py -g > download/Version.cfg
