#! /bin/sh -x
##
## runtest.sh -- run some tests for Tim
##
## This does everything you need to test yer data.  You may want to skip
## the rebal steps if you've recently moved some of your messages
## (because they were in the wrong corpus) or you may suffer my fate and
## get stuck forever re-categorizing email.
##
## Just set up your messages as detailed in README.txt; put them all in
## the reservoir directories, and this script will take care of the
## rest.  Paste the output (also in results.txt) to the mailing list for
## good karma.
##
## Neale Pickett <neale@woozle.org>
##

if [ "$1" = "-r" ]; then
    REBAL=1
    shift
fi

# Which test to run
TEST=${1:-robinson1}

# Number of messages per rebalanced set
RNUM=200

# Number of sets
SETS=5

if [ -n "$REBAL" ]; then
    # Put them all into reservoirs
    python rebal.py -r Data/Ham/reservoir -s Data/Ham/Set -n 0 -Q
    python rebal.py -r Data/Spam/reservoir -s Data/Spam/Set -n 0 -Q
    # Rebalance
    python rebal.py -r Data/Ham/reservoir -s Data/Ham/Set -n $RNUM -Q
    python rebal.py -r Data/Spam/reservoir -s Data/Spam/Set -n $RNUM -Q
fi

case "$TEST" in
    run2|useold)
	python timcv.py -n $SETS > run2.txt

        python rates.py run1 run2 > runrates.txt

        python cmp.py run1s run2s | tee results.txt
	;;
    robinson1)
	# This test requires you have an appropriately-modified
	# Tester.py.new and classifier.py.new as detailed in
	# <LNBBLJKPBEHFEDALKOLCKENMBEAB.tim.one@comcast.net>

	python timcv.py -n $SETS > run1.txt

	mv Tester.py Tester.py.orig
	cp Tester.py.new Tester.py
	mv classifier.py classifier.py.orig
	cp classifier.py.new classifier.py
	python timcv.py -n $SETS > run2.txt

	python rates.py run1 run2 > runrates.txt

        python cmp.py run1s run2s | tee results.txt

	mv Tester.py.orig Tester.py
	mv classifier.py.orig classifier.py
	;;
    mass)
	## Tim took this code out, don't run this test.  I'm leaving
	## this stuff in here for the time being so I can refer to it
	## later when I need to do this sort of thing again :)

        # Clear out .ini file
        rm -f bayescustomize.ini
        # Run 1
	python timcv.py -n $SETS > run1.txt
        # New .ini file
	cat > bayescustomize.ini <<EOF
[Classifier]
adjust_probs_by_evidence_mass: True
min_spamprob: 0.001
max_spamprob: 0.999
hambias: 1.5
EOF
        # Run 2
	python timcv.py -n $SETS > run2.txt
        # Generate rates
	python rates.py run1 run2 > runrates.txt
        # Compare rates
	python cmp.py run1s run2s | tee results.txt
	;;
esac
