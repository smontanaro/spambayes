#! /usr/bin/env python
# At the moment, this requires Python 2.3 from CVS (heapq, Set, enumerate).

# A test driver using "the standard" test directory structure.  See also
# rates.py and cmp.py for summarizing results.

"""Usage: %(program)s [options]

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
import Options

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

def printmsg(msg, prob, clues, charlimit=None):
    print msg.tag
    print "prob =", prob
    for clue in clues:
        print "prob(%r) = %g" % clue
    print
    guts = str(msg)
    if charlimit is not None:
        guts = guts[:charlimit]
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

    def __init__(self, nbuckets=40):
        self.nbuckets = nbuckets
        self.falsepos = Set()
        self.falseneg = Set()
        self.global_ham_hist = Hist(self.nbuckets)
        self.global_spam_hist = Hist(self.nbuckets)

    def train(self, ham, spam):
        self.classifier = classifier.GrahamBayes()
        t = self.tester = Tester.Test(self.classifier)

        print "Training on", ham, "&", spam, "...",
        t.train(ham, spam)
        print t.nham, "hams &", t.nspam, "spams"

        self.trained_ham_hist = Hist(self.nbuckets)
        self.trained_spam_hist = Hist(self.nbuckets)

        #f = file('w.pik', 'wb')
        #pickle.dump(self.classifier, f, 1)
        #f.close()
        #import sys
        #sys.exit(0)

    def finishtest(self):
        printhist("all in this training set:",
                  self.trained_ham_hist, self.trained_spam_hist)
        self.global_ham_hist += self.trained_ham_hist
        self.global_spam_hist += self.trained_spam_hist

    def alldone(self):
        printhist("all runs:", self.global_ham_hist, self.global_spam_hist)

    def test(self, ham, spam, charlimit=None):
        c = self.classifier
        t = self.tester
        local_ham_hist = Hist(self.nbuckets)
        local_spam_hist = Hist(self.nbuckets)

        def new_ham(msg, prob):
            local_ham_hist.add(prob)

        def new_spam(msg, prob):
            local_spam_hist.add(prob)
            if prob < 0.1:
                print
                print "Low prob spam!", prob
                prob, clues = c.spamprob(msg, True)
                printmsg(msg, prob, clues, charlimit)

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
        for e in newfpos:
            print '*' * 78
            prob, clues = c.spamprob(e, True)
            printmsg(e, prob, clues, charlimit)

        newfneg = Set(t.false_negatives()) - self.falseneg
        self.falseneg |= newfneg
        print "    new false negatives:", [e.tag for e in newfneg]
        for e in []:#newfneg:
            print '*' * 78
            prob, clues = c.spamprob(e, True)
            printmsg(e, prob, clues, 1000)

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

        printhist("this pair:", local_ham_hist, local_spam_hist)
        self.trained_ham_hist += local_ham_hist
        self.trained_spam_hist += local_spam_hist

def drive(nsets):
    print Options.options.display()

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

    Options.options.mergefiles(['bayescustomize.ini'])
    drive(nsets)
