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

# Number of messages per rebalanced set
RNUM=200

# Number of sets
SETS=5

# Put them all into reservoirs
python rebal.py -r Data/Ham/reservoir -s Data/Ham/Set -n 0 -Q
python rebal.py -r Data/Spam/reservoir -s Data/Spam/Set -n 0 -Q
# Rebalance
python rebal.py -r Data/Ham/reservoir -s Data/Ham/Set -n $RNUM -Q
python rebal.py -r Data/Spam/reservoir -s Data/Spam/Set -n $RNUM -Q
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
