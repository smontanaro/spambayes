
#
# GNU Makefile to make it easy to run timcv.
#
# To use, create a pair of SpamBayes config files, e.g., std.ini and
# trial.ini, then execute
#
#    make BASE=std TRIAL=trial
#
# The final output will be in std-trial.txt.
#
# Since the default value for BASE and TRIAL are "std" and "trial",
# respectively, the above can be abbreviated to
#
#    make
#
# If you want to compare multiple trial configurations against a single
# standard configuration, execute (for example):
#
#    make TRIAL=trial1
#    make TRIAL=trial2
#
# (assuming your baseline configuration is in std.ini).  The Makefile will
# avoid running timcv.py against the standard configuration unnecessarily,
# speeding things up a bit.
#
# This Makefile assumes the availability of GNU make.  It uses both the
# $(shell ...) and $(wildcard ...) constructs.  It also assumes your
# SpamBayes source tree is rooted at ~/src/spambayes.
#

SBDIR=$(HOME)/src/spambayes
TIMCV=$(SBDIR)/testtools/timcv.py
RATE=$(SBDIR)/testtools/rates.py
CMP=$(SBDIR)/testtools/cmp.py
NDIR=$(shell ls -d Data/Ham/Set* | wc -l)

BASE=std
TRIAL=trial

DATA=$(wildcard Data/Ham/* Data/Spam/*)

all : $(BASE)-$(TRIAL).txt

$(BASE)-$(TRIAL).txt : $(BASE)s.txt $(TRIAL)s.txt
	python $(CMP) $(BASE)s.txt $(TRIAL)s.txt > $(BASE)-$(TRIAL).txt

$(BASE)s.txt : $(BASE).txt
	python $(RATE) $(BASE)

$(TRIAL)s.txt : $(TRIAL).txt
	python $(RATE) $(TRIAL)

$(BASE).txt : $(BASE).ini $(DATA)
	BAYESCUSTOMIZE=$(BASE).ini python $(TIMCV) -n $(NDIR) -s 12345 > $(BASE).txt

$(TRIAL).txt : $(TRIAL).ini $(DATA)
	BAYESCUSTOMIZE=$(TRIAL).ini python $(TIMCV) -n $(NDIR) -s 12345 > $(TRIAL).txt

clean : FORCE
	rm -f $(BASE)-$(TRIAL).txt $(BASE)*.txt $(TRIAL)*.txt

FORCE :
