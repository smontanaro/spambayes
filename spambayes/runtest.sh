#! /bin/sh -e
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
## rest.  Paste the output to the mailing list for good karma.
##
## Neale Pickett <neale@woozle.org>
##

if [ "$1" = "-r" ]; then
    REBAL=1
    shift
fi

# Include local directory in Python path
if [ -n "$PYTHONPATH" ]; then
    PYTHONPATH=$PYTHONPATH:.
else
    PYTHONPATH=.
fi
export PYTHONPATH

# Which test to run
TEST=${1:-run2}

# Number of messages per rebalanced set
RNUM=${REBAL_RNUM:-200}

# Number of sets
case ${REBAL_SETS:-undefined} in
undefined)
    # count the number of sets
    i=1
    while [ -d Data/Ham/Set$i -a -d Data/Spam/Set$i ]; do
	i=`expr $i + 1`
    done
    SETS=`expr $i - 1`
    ;;
*)
    # use the provided value
    SETS=${REBAL_SETS}
    ;;
esac

set -x

if [ -n "$REBAL" ]; then
    # Put them all into reservoirs
    python utilities/rebal.py -r Data/Ham/reservoir -s Data/Ham/Set -n 0 -q
    python utilities/rebal.py -r Data/Spam/reservoir -s Data/Spam/Set -n 0 -q
    # Rebalance
    python utilities/rebal.py -r Data/Ham/reservoir -s Data/Ham/Set -n $RNUM -q -Q
    python utilities/rebal.py -r Data/Spam/reservoir -s Data/Spam/Set -n $RNUM -q -Q
fi

case "$TEST" in
    test1)
	python testtools/timtest.py -n $SETS > test1.txt
	;;
    test2)
	python testtools/timtest.py -n $SETS > test2.txt
	;;
    timcv1|cv1)
	python testtools/timcv.py -n $SETS > cv1.txt
	;;
    timcv2|cv2)
	python testtools/timcv.py -n $SETS > cv2.txt

        python testtools/rates.py cv1 cv2 > runrates.txt

        python testtools/cmp.py cv1s cv2s | tee results.txt
	;;
    *)
	echo "Available targets:"
	sed -n 's/^\(  *[a-z0-9|]*\))$/\1/p' $0
	;;
esac
