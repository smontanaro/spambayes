#! /usr/bin/env python

NSETS = 5
SPAMDIRS = ["Data/Spam/Set%d" % i for i in range(1, NSETS+1)]
HAMDIRS  = ["Data/Ham/Set%d" % i for i in range(1, NSETS+1)]
SPAMHAMDIRS = zip(SPAMDIRS, HAMDIRS)

import os
from sets import Set
import cPickle as pickle

import Tester
import classifier
from timtoken import tokenize

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

class MsgStream(object):
    def __init__(self, directory):
        self.directory = directory

    def produce(self):
        directory = self.directory
        for fname in os.listdir(directory):
            yield Msg(directory, fname)

    def __iter__(self):
        return self.produce()

class Driver:

    def __init__(self):
        self.nbuckets = 40
        self.falsepos = Set()
        self.falseneg = Set()
        self.global_ham_hist = Hist(self.nbuckets)
        self.global_spam_hist = Hist(self.nbuckets)

    def train(self, ham, spam):
        self.classifier = classifier.GrahamBayes()
        self.tester = Tester.Test(self.classifier)
        print "Training on", ham, "&", spam, "..."
        self.tester.train(ham, spam)

        self.trained_ham_hist = Hist(self.nbuckets)
        self.trained_spam_hist = Hist(self.nbuckets)

    def finish(self):
        printhist("all in this set:",
                  self.trained_ham_hist, self.trained_spam_hist)
        self.global_ham_hist += self.trained_ham_hist
        self.global_spam_hist += self.trained_spam_hist

    def alldone(self):
        printhist("all runs:", self.global_ham_hist, self.global_spam_hist)

    def test(self, ham, spam):
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
                print msg.tag
                prob, clues = c.spamprob(msg, True)
                for clue in clues:
                    print "prob(%r) = %g" % clue
                print
                print msg.guts

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
            print e.tag
            prob, clues = c.spamprob(e, True)
            print "prob =", prob
            for clue in clues:
                print "prob(%r) = %g" % clue
            print
            print e.guts

        newfneg = Set(t.false_negatives()) - self.falseneg
        self.falseneg |= newfneg
        print "    new false negatives:", [e.tag for e in newfneg]
        for e in []:#newfneg:
            print '*' * 78
            print e.tag
            prob, clues = c.spamprob(e, True)
            print "prob =", prob
            for clue in clues:
                print "prob(%r) = %g" % clue
            print
            print e.guts[:1000]

        print
        print "    best discriminators:"
        stats = [(r.killcount, w) for w, r in c.wordinfo.iteritems()]
        stats.sort()
        del stats[:-30]
        for count, w in stats:
            r = c.wordinfo[w]
            print "        %r %d %g" % (w, r.killcount, r.spamprob)


        printhist("this pair:", local_ham_hist, local_spam_hist)

        self.trained_ham_hist += local_ham_hist
        self.trained_spam_hist += local_spam_hist

def jdrive():
    d = Driver()

    for spamdir, hamdir in SPAMHAMDIRS:
        d.train(MsgStream(hamdir), MsgStream(spamdir))
        for sd2, hd2 in SPAMHAMDIRS:
            if (sd2, hd2) == (spamdir, hamdir):
                continue
            d.test(MsgStream(hd2), MsgStream(sd2))
        d.finish()
    d.alldone()

def drive():
    nbuckets = 40
    falsepos = Set()
    falseneg = Set()
    global_ham_hist = Hist(nbuckets)
    global_spam_hist = Hist(nbuckets)
    for spamdir, hamdir in SPAMHAMDIRS:
        c = classifier.GrahamBayes()
        t = Tester.Test(c)
        print "Training on", hamdir, "&", spamdir, "...",
        t.train(MsgStream(hamdir), MsgStream(spamdir))
        print t.nham, "hams &", t.nspam, "spams"

        trained_ham_hist = Hist(nbuckets)
        trained_spam_hist = Hist(nbuckets)

        fp = file('w.pik', 'wb')
        pickle.dump(c, fp, 1)
        fp.close()

        for sd2, hd2 in SPAMHAMDIRS:
            if (sd2, hd2) == (spamdir, hamdir):
                continue

            local_ham_hist = Hist(nbuckets)
            local_spam_hist = Hist(nbuckets)

            def new_ham(msg, prob):
                local_ham_hist.add(prob)

            def new_spam(msg, prob):
                local_spam_hist.add(prob)
                if prob < 0.1:
                    print
                    print "Low prob spam!", prob
                    print msg.path
                    prob, clues = c.spamprob(msg, True)
                    for clue in clues:
                        print "prob(%r) = %g" % clue
                    print
                    print msg.guts

            t.reset_test_results()
            print "    testing against", hd2, "&", sd2, "...",
            t.predict(MsgStream(sd2), True, new_spam)
            t.predict(MsgStream(hd2), False, new_ham)
            print t.nham_tested, "hams &", t.nspam_tested, "spams"

            print "    false positive:", t.false_positive_rate()
            print "    false negative:", t.false_negative_rate()

            newfpos = Set(t.false_positives()) - falsepos
            falsepos |= newfpos
            print "    new false positives:", [e.path for e in newfpos]
            for e in newfpos:
                print '*' * 78
                print e.path
                prob, clues = c.spamprob(e, True)
                print "prob =", prob
                for clue in clues:
                    print "prob(%r) = %g" % clue
                print
                print e.guts

            newfneg = Set(t.false_negatives()) - falseneg
            falseneg |= newfneg
            print "    new false negatives:", [e.path for e in newfneg]
            for e in []:#newfneg:
                print '*' * 78
                print e.path
                prob, clues = c.spamprob(e, True)
                print "prob =", prob
                for clue in clues:
                    print "prob(%r) = %g" % clue
                print
                print e.guts[:1000]

            print
            print "    best discriminators:"
            stats = [(r.killcount, w) for w, r in c.wordinfo.iteritems()]
            stats.sort()
            del stats[:-30]
            for count, w in stats:
                r = c.wordinfo[w]
                print "        %r %d %g" % (w, r.killcount, r.spamprob)


            printhist("this pair:", local_ham_hist, local_spam_hist)

            trained_ham_hist += local_ham_hist
            trained_spam_hist += local_spam_hist

        printhist("all in this set:", trained_ham_hist, trained_spam_hist)
        global_ham_hist += trained_ham_hist
        global_spam_hist += trained_spam_hist

    printhist("all runs:", global_ham_hist, global_spam_hist)

if __name__ == "__main__":
    drive()
