#! /usr/bin/env python
# At the moment, this requires Python 2.3 from CVS (heapq, Set, enumerate).

# A test driver using "the standard" test directory structure.  See also
# rates.py and cmp.py for summarizing results.

"""Usage: %(program)s [-h] -n nsets

Where:
    -h
        Show usage and exit.
    -n int
        Number of Set directories (Data/Spam/Set1, ... and Data/Ham/Set1, ...).
        This is required.

In addition, an attempt is made to merge bayescustomize.ini into the options.
If that exists, it can be used to change the settings in Options.options.
"""

import os
import sys
from sets import Set
import cPickle as pickle
from heapq import heapreplace

import Tester
import classifier
from tokenizer import tokenize
from Options import options

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class Hist:
    def __init__(self, nbuckets=20):
        self.buckets = [0] * nbuckets
        self.nbuckets = nbuckets

    def add(self, x):
        n = self.nbuckets
        i = int(n * x)
        if i >= n:
            i = n-1
        self.buckets[i] += 1

    def __iadd__(self, other):
        if self.nbuckets != other.nbuckets:
            raise ValueError('bucket size mismatch')
        for i in range(self.nbuckets):
            self.buckets[i] += other.buckets[i]
        return self

    def display(self, WIDTH=60):
        biggest = max(self.buckets)
        hunit, r = divmod(biggest, WIDTH)
        if r:
            hunit += 1
        print "* =", hunit, "items"

        ndigits = len(str(biggest))
        format = "%6.2f %" + str(ndigits) + "d"

        for i, n in enumerate(self.buckets):
            print format % (100.0 * i / self.nbuckets, n),
            print '*' * ((n + hunit - 1) // hunit)

def printhist(tag, ham, spam):
    print
    print "Ham distribution for", tag
    ham.display()

    print
    print "Spam distribution for", tag
    spam.display()

def printmsg(msg, prob, clues):
    print msg.tag
    print "prob =", prob
    for clue in clues:
        print "prob(%r) = %g" % clue
    print
    guts = str(msg)
    if options.show_charlimit > 0:
        guts = guts[:options.show_charlimit]
    print guts

class Msg(object):
    def __init__(self, dir, name):
        path = dir + "/" + name
        self.tag = path
        f = open(path, 'rb')
        guts = f.read()
        f.close()
        self.guts = guts

    def __iter__(self):
        return tokenize(self.guts)

    def __hash__(self):
        return hash(self.tag)

    def __eq__(self, other):
        return self.tag == other.tag

    def __str__(self):
        return self.guts

class MsgStream(object):
    def __init__(self, directory):
        self.directory = directory

    def __str__(self):
        return self.directory

    def produce(self):
        directory = self.directory
        for fname in os.listdir(directory):
            yield Msg(directory, fname)

    def xproduce(self):
        import random
        directory = self.directory
        all = os.listdir(directory)
        random.seed(hash(directory))
        random.shuffle(all)
        for fname in all[-1500:-1000:]:
            yield Msg(directory, fname)

    def __iter__(self):
        return self.produce()


# Loop:
#     train() # on ham and spam
#     Loop:
#         test()   # on presumably new ham and spam
#     finishtest() # display stats against all runs on training set
# alldone()   # display stats against all runs

class Driver:

    def __init__(self):
        self.falsepos = Set()
        self.falseneg = Set()
        self.global_ham_hist = Hist(options.nbuckets)
        self.global_spam_hist = Hist(options.nbuckets)
        self.ntimes_train_called = 0

    def train(self, ham, spam):
        self.classifier = classifier.GrahamBayes()
        t = self.tester = Tester.Test(self.classifier)

        print "Training on", ham, "&", spam, "...",
        t.train(ham, spam)
        print t.nham, "hams &", t.nspam, "spams"

        self.trained_ham_hist = Hist(options.nbuckets)
        self.trained_spam_hist = Hist(options.nbuckets)

        self.ntimes_train_called += 1
        if options.save_trained_pickles:
            fname = "%s%d.pik" % (options.pickle_basename,
                                  self.ntimes_train_called)
            print "    saving pickle to", fname
            fp = file(fname, 'wb')
            pickle.dump(self.classifier, fp, 1)
            fp.close()

    def finishtest(self):
        if options.show_histograms:
            printhist("all in this training set:",
                      self.trained_ham_hist, self.trained_spam_hist)
        self.global_ham_hist += self.trained_ham_hist
        self.global_spam_hist += self.trained_spam_hist

    def alldone(self):
        if options.show_histograms:
            printhist("all runs:", self.global_ham_hist, self.global_spam_hist)

    def test(self, ham, spam):
        c = self.classifier
        t = self.tester
        local_ham_hist = Hist(options.nbuckets)
        local_spam_hist = Hist(options.nbuckets)

        def new_ham(msg, prob, lo=options.show_ham_lo,
                               hi=options.show_ham_hi):
            local_ham_hist.add(prob)
            if lo <= prob <= hi:
                print
                print "Ham with prob =", prob
                prob, clues = c.spamprob(msg, True)
                printmsg(msg, prob, clues)

        def new_spam(msg, prob, lo=options.show_spam_lo,
                                hi=options.show_spam_hi):
            local_spam_hist.add(prob)
            if lo <= prob <= hi:
                print
                print "Spam with prob =", prob
                prob, clues = c.spamprob(msg, True)
                printmsg(msg, prob, clues)

        t.reset_test_results()
        print "    testing against", ham, "&", spam, "...",
        t.predict(spam, True, new_spam)
        t.predict(ham, False, new_ham)
        print t.nham_tested, "hams &", t.nspam_tested, "spams"

        print "    false positive:", t.false_positive_rate()
        print "    false negative:", t.false_negative_rate()

        newfpos = Set(t.false_positives()) - self.falsepos
        self.falsepos |= newfpos
        print "    new false positives:", [e.tag for e in newfpos]
        if not options.show_false_positives:
            newfpos = ()
        for e in newfpos:
            print '*' * 78
            prob, clues = c.spamprob(e, True)
            printmsg(e, prob, clues)

        newfneg = Set(t.false_negatives()) - self.falseneg
        self.falseneg |= newfneg
        print "    new false negatives:", [e.tag for e in newfneg]
        if not options.show_false_negatives:
            newfneg = ()
        for e in newfneg:
            print '*' * 78
            prob, clues = c.spamprob(e, True)
            printmsg(e, prob, clues)

        if options.show_best_discriminators:
            print
            print "    best discriminators:"
            stats = [(-1, None) for i in range(30)]
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

        if options.show_histograms:
            printhist("this pair:", local_ham_hist, local_spam_hist)
        self.trained_ham_hist += local_ham_hist
        self.trained_spam_hist += local_spam_hist

def drive(nsets):
    print options.display()

    spamdirs = ["Data/Spam/Set%d" % i for i in range(1, nsets+1)]
    hamdirs  = ["Data/Ham/Set%d" % i for i in range(1, nsets+1)]
    spamhamdirs = zip(spamdirs, hamdirs)

    d = Driver()
    for spamdir, hamdir in spamhamdirs:
        d.train(MsgStream(hamdir), MsgStream(spamdir))
        for sd2, hd2 in spamhamdirs:
            if (sd2, hd2) == (spamdir, hamdir):
                continue
            d.test(MsgStream(hd2), MsgStream(sd2))
        d.finishtest()
    d.alldone()

if __name__ == "__main__":
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:')
    except getopt.error, msg:
        usage(1, msg)

    nsets = None
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)

    if args:
        usage(1, "Positional arguments not supported")
    if nsets is None:
        usage(1, "-n is required")

    drive(nsets)
