#! /usr/bin/env python

# A test driver using "the standard" test directory structure, producing
# info about the internals of the central-limit schemes.

"""Usage: %(program)s  [options] -n nsets -t int,int,...,int

Scores for all predictions are saved at the end to binary pickle clim.pik.
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
        Number of Set directories (Data/Spam/Set1, ... and Data/Ham/Set1, ...).
        This is required.

    -t int,int,...,int
        Build a classifier training on these Set directories.
        This is used to predict against the remaining Set directories.
        This is required.

If you only want to use some of the messages in each set,

    --ham-keep int
        The maximum number of msgs to use from each Ham set.  The msgs are
        chosen randomly.  See also the -s option.

    --spam-keep int
        The maximum number of msgs to use from each Spam set.  The msgs are
        chosen randomly.  See also the -s option.

    -s int
        A seed for the random number generator.  Has no effect unless
        at least on of {--ham-keep, --spam-keep} is specified.  If -s
        isn't specifed, the seed is taken from current time.

In addition, an attempt is made to merge bayescustomize.ini into the options.
If that exists, it can be used to change the settings in Options.options.
"""

from __future__ import generators

import sys
from heapq import heapreplace
from sets import Set
import cPickle as pickle

from Options import options
import TestDriver
from TestDriver import printmsg
import msgs
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

class MyDriver(TestDriver.Driver):

    def __init__(self):
        TestDriver.Driver.__init__(self)
        # tuples of (msg.tag, is_spam, zham, zspam, hmean, smean, n)
        self.all_ham = []
        self.all_spam = []

    def test(self, ham, spam):
        c = self.classifier
        t = self.tester
        local_ham_hist = Hist()
        local_spam_hist = Hist()

        # clues start with these:
        #    extra = [('*zham*', zham),
        #             ('*zspam*', zspam),
        #             ('*hmean*', hmean),   # raw mean as ham
        #             ('*smean*', smean),   # raw mean as spam
        #             ('*n*', n),
        #
        # For use_central_limit, hmean and smean have the same value.

        def new_ham(msg, prob, getclues=c.spamprob):
            local_ham_hist.add(prob * 100.0)
            prob, clues = getclues(msg, True)
            stuff = tuple([val for tag, val in clues[:5]])
            self.all_ham.append((msg.tag, False) + stuff)

        def new_spam(msg, prob, getclues=c.spamprob):
            local_spam_hist.add(prob * 100.0)
            prob, clues = getclues(msg, True)
            stuff = tuple([val for tag, val in clues[:5]])
            self.all_spam.append((msg.tag, True) + stuff)

        t.reset_test_results()
        print "-> Predicting", ham, "&", spam, "..."
        t.predict(spam, True, new_spam)
        t.predict(ham, False, new_ham)
        print "-> <stat> tested", t.nham_tested, "hams &", t.nspam_tested, \
              "spams against", c.nham, "hams &", c.nspam, "spams"

        print "-> <stat> false positive %:", t.false_positive_rate()
        print "-> <stat> false negative %:", t.false_negative_rate()

        newfpos = Set(t.false_positives()) - self.falsepos
        self.falsepos |= newfpos
        print "-> <stat> %d new false positives" % len(newfpos)
        if newfpos:
            print "    new fp:", [e.tag for e in newfpos]
        if not options.show_false_positives:
            newfpos = ()
        for e in newfpos:
            print '*' * 78
            prob, clues = c.spamprob(e, True)
            printmsg(e, prob, clues)

        newfneg = Set(t.false_negatives()) - self.falseneg
        self.falseneg |= newfneg
        print "-> <stat> %d new false negatives" % len(newfneg)
        if newfneg:
            print "    new fn:", [e.tag for e in newfneg]
        if not options.show_false_negatives:
            newfneg = ()
        for e in newfneg:
            print '*' * 78
            prob, clues = c.spamprob(e, True)
            printmsg(e, prob, clues)

        if options.show_best_discriminators > 0:
            print
            print "    best discriminators:"
            stats = [(-1, None)] * options.show_best_discriminators
            smallest_killcount = -1
            for w, r in c.wordinfo.iteritems():
                if r.killcount > smallest_killcount:
                    heapreplace(stats, (r.killcount, w))
                    smallest_killcount = stats[0][0]
            stats.sort()
            for count, w in stats:
                if count < 0:
                    continue
                r = c.wordinfo[w]
                print "        %r %d %g" % (w, r.killcount, r.spamprob)

        self.trained_ham_hist = local_ham_hist
        self.trained_spam_hist = local_spam_hist

def ints_to_string(x):
    return '{' + ','.join(map(str, x)) + '}'

def drive(nsets, trainon, predicton):
    print options.display()

    spamdirs = [options.spam_directories % i for i in range(1, nsets+1)]
    hamdirs  = [options.ham_directories % i for i in range(1, nsets+1)]

    train_hamdirs = [hamdirs[i-1] for i in trainon]
    train_spamdirs = [spamdirs[i-1] for i in trainon]
    predict_hamdirs = [hamdirs[i-1] for i in predicton]
    predict_spamdirs = [spamdirs[i-1] for i in predicton]
    trainints = ints_to_string(trainon)
    predictints = ints_to_string(predicton)

    d = MyDriver()
    hamroot = options.ham_directories[:-2] # lose trailing %d
    spamroot = options.spam_directories[:-2]

    d.train(msgs.HamStream(hamroot + trainints, train_hamdirs),
            msgs.SpamStream(spamroot + trainints, train_spamdirs))
    c = d.classifier
    print '-> <stat> population hammean', c.hammean, 'hamvar', c.hamvar
    print '-> <stat> population spammean', c.spammean, 'spamvar', c.spamvar

    d.test(msgs.HamStream(hamroot + predictints, predict_hamdirs),
           msgs.SpamStream(spamroot + predictints, predict_spamdirs))

    d.finishtest()
    d.alldone()

    print "Saving all score data to pickle", fname
    f = file(fname, 'wb')
    pickle.dump(d.all_ham, f, 1)
    pickle.dump(d.all_spam, f, 1)
    f.close()

def main():
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:s:t:',
                                   ['ham-keep=', 'spam-keep='])
    except getopt.error, msg:
        usage(1, msg)

    nsets = seed = hamkeep = spamkeep = trainon = None
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)
        elif opt == '-s':
            seed = int(arg)
        elif opt == '-t':
            trainon = Set(map(int, arg.split(',')))
        elif opt == '--ham-keep':
            hamkeep = int(arg)
        elif opt == '--spam-keep':
            spamkeep = int(arg)

    if args:
        usage(1, "Positional arguments not supported")
    if nsets is None:
        usage(1, "-n is required")
    if not trainon:
        usage(1, "-t is required")
    predicton = list(Set(range(1, nsets+1)) - trainon)
    trainon = list(trainon)
    predicton.sort()
    trainon.sort()

    msgs.setparms(hamkeep, spamkeep, seed)
    drive(nsets, trainon, predicton)

if __name__ == "__main__":
    main()
