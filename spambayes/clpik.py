#! /usr/bin/env python

# Analyze a clim.pik file.

"""Usage: %(program)s  [options] [central_limit_pickle_file]

An example analysis program showing to access info from a central-limit
pickle file created by clgen.py.  This program produces histograms of
various things.

Scores for all predictions are saved at the end of binary pickle clim.pik.
This contains two lists of tuples, the first list with a tuple for every
ham predicted, the second list with a tuple for every spam predicted.  Each
tuple has these values:

    tag         the msg identifier
    is_spam     True if msg came from a spam Set, False if from a ham Set
    zham        the msg zscore relative to the population ham
    zspam       the msg zscore relative to the population spam
    hmean       the raw mean ham score
    smean       the raw mean spam score
    n           the number of clues used to judge this msg

Note that hmean and smean are the same under use_central_limit; they're
very likely to differ under use_central_limit2.

Where:
    -h
        Show usage and exit.
    -n int
        Number of histogram buckets to display.  Default 100.

If no file is named on the cmdline, clim.pik is used.
"""

import sys
import cPickle as pickle

from Histogram import Hist

fname = 'clim.pik'

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def dump(nbuckets, tag, n, hmean, zham, smean, zspam):
    for msg, hist in [('# words', n),
                      ('ham mean', hmean),
                      ('ham zscore', zham),
                      ('spam mean', smean),
                      ('spam zscore', zspam)]:
        print
        print tag, msg + ':',
        hist.display(nbuckets)

def drive(fname, nbuckets):
    print 'Reading', fname, '...'
    f = open(fname, 'rb')
    ham = pickle.load(f)
    spam = pickle.load(f)
    f.close()

    print 'Building histograms for', len(ham), 'ham &', len(spam), 'spam'
    ham_n = Hist(lo=None, hi=None)
    spam_n = Hist(lo=None, hi=None)

    ham_as_ham_mean   = Hist(lo=None, hi=None)
    ham_as_spam_mean  = Hist(lo=None, hi=None)
    spam_as_ham_mean  = Hist(lo=None, hi=None)
    spam_as_spam_mean = Hist(lo=None, hi=None)

    ham_as_ham_zscore   = Hist(lo=None, hi=None)
    ham_as_spam_zscore  = Hist(lo=None, hi=None)
    spam_as_ham_zscore  = Hist(lo=None, hi=None)
    spam_as_spam_zscore = Hist(lo=None, hi=None)

    for msgid, is_spam, zham, zspam, hmean, smean, n in ham:
        ham_n.add(n)
        ham_as_ham_mean.add(hmean)
        ham_as_ham_zscore.add(zham)
        ham_as_spam_mean.add(smean)
        ham_as_spam_zscore.add(zspam)

    dump(nbuckets, 'ham', ham_n, ham_as_ham_mean, ham_as_ham_zscore,
         ham_as_spam_mean, ham_as_spam_zscore)

    for msgid, is_spam, zham, zspam, hmean, smean, n in spam:
        spam_n.add(n)
        spam_as_ham_mean.add(hmean)
        spam_as_ham_zscore.add(zham)
        spam_as_spam_mean.add(smean)
        spam_as_spam_zscore.add(zspam)

    dump(nbuckets, 'spam', spam_n, spam_as_ham_mean, spam_as_ham_zscore,
         spam_as_spam_mean, spam_as_spam_zscore)

def main():
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:',
                                   ['ham-keep=', 'spam-keep='])
    except getopt.error, msg:
        usage(1, msg)

    nbuckets = 100
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nbuckets = int(arg)

    fname = 'clim.pik'
    if args:
        fname = args.pop(0)
    if args:
        usage(1, "No more than one positional argument allowed")

    drive(fname, nbuckets)

if __name__ == "__main__":
    main()
