# Loop:
#     Optional:
#         # Set up a new base classifier for testing.
#         new_classifier()
#     # Run tests against (possibly variants of) this classifier.
#     Loop:
#         Loop:
#             Optional:
#                 # train on more ham and spam
#                 train(ham, spam)
#             Optional:
#                 # Forget training for some subset of ham and spam.
#                 untrain(ham, spam)
#         # Predict against other data.
#         Loop:
#             test(ham, spam)
#         # Display stats against all runs on this classifier variant.
#         # This also saves the trained classifer, if desired (option
#         # save_trained_pickles).
#         finishtest()
# # Display stats against all runs.
# alldone()

from sets import Set
import cPickle as pickle
from heapq import heapreplace

from Options import options
import Tester
import classifier

class Hist:
    """Simple histograms of float values in [0.0, 1.0]."""

    def __init__(self, nbuckets=20):
        self.buckets = [0] * nbuckets
        self.nbuckets = nbuckets
        self.n = 0          # number of data points
        self.sum = 0.0      # sum of their values
        self.sumsq = 0.0    # sum of their squares

    def add(self, x):
        n = self.nbuckets
        i = int(n * x)
        if i >= n:
            i = n-1
        self.buckets[i] += 1

        self.n += 1
        x *= 100.0
        self.sum += x
        self.sumsq += x*x

    def __iadd__(self, other):
        if self.nbuckets != other.nbuckets:
            raise ValueError('bucket size mismatch')
        for i in range(self.nbuckets):
            self.buckets[i] += other.buckets[i]
        self.n += other.n
        self.sum += other.sum
        self.sumsq += other.sumsq
        return self

    def display(self, WIDTH=60):
        from math import sqrt
        if self.n > 1:
            mean = self.sum / self.n
            # sum (x_i - mean)**2 = sum (x_i**2 - 2*x_i*mean + mean**2) =
            # sum x_i**2 - 2*mean*sum x_i + sum mean**2 =
            # sum x_i**2 - 2*mean*mean*n + n*mean**2 =
            # sum x_i**2 - n*mean**2
            samplevar = (self.sumsq - self.n * mean**2) / (self.n - 1)
            print "%d items; mean %.2f; sample sdev %.2f" % (self.n,
                  mean, sqrt(samplevar))

        biggest = max(self.buckets)
        hunit, r = divmod(biggest, WIDTH)
        if r:
            hunit += 1
        print "* =", hunit, "items"

        ndigits = len(str(biggest))
        format = "%6.2f %" + str(ndigits) + "d"

        for i in range(len(self.buckets)):
            n = self.buckets[i]
            print format % (100.0 * i / self.nbuckets, n),
            print '*' * ((n + hunit - 1) // hunit)

def printhist(tag, ham, spam):
    print
    print "-> <stat> Ham scores for", tag,
    ham.display()

    print
    print "-> <stat> Spam scores for", tag,
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

class Driver:

    def __init__(self):
        self.falsepos = Set()
        self.falseneg = Set()
        self.global_ham_hist = Hist(options.nbuckets)
        self.global_spam_hist = Hist(options.nbuckets)
        self.ntimes_finishtest_called = 0
        self.new_classifier()

    def new_classifier(self):
        c = self.classifier = classifier.GrahamBayes()
        self.tester = Tester.Test(c)
        self.trained_ham_hist = Hist(options.nbuckets)
        self.trained_spam_hist = Hist(options.nbuckets)

    # CAUTION:  this just doesn't work for incrememental training when
    # options.use_central_limit is in effect.
    def train(self, ham, spam):
        print "-> Training on", ham, "&", spam, "...",
        c = self.classifier
        nham, nspam = c.nham, c.nspam
        self.tester.train(ham, spam)
        print c.nham - nham, "hams &", c.nspam- nspam, "spams"
        c.compute_population_stats(ham, False)
        c.compute_population_stats(spam, True)

    # CAUTION:  this just doesn't work for incrememental training when
    # options.use_central_limit is in effect.
    def untrain(self, ham, spam):
        print "-> Forgetting", ham, "&", spam, "...",
        c = self.classifier
        nham, nspam = c.nham, c.nspam
        self.tester.untrain(ham, spam)
        print nham - c.nham, "hams &", nspam - c.nspam, "spams"

    def finishtest(self):
        if options.show_histograms:
            printhist("all in this training set:",
                      self.trained_ham_hist, self.trained_spam_hist)
        self.global_ham_hist += self.trained_ham_hist
        self.global_spam_hist += self.trained_spam_hist
        self.trained_ham_hist = Hist(options.nbuckets)
        self.trained_spam_hist = Hist(options.nbuckets)

        self.ntimes_finishtest_called += 1
        if options.save_trained_pickles:
            fname = "%s%d.pik" % (options.pickle_basename,
                                  self.ntimes_finishtest_called)
            print "    saving pickle to", fname
            fp = file(fname, 'wb')
            pickle.dump(self.classifier, fp, 1)
            fp.close()

    def alldone(self):
        if options.show_histograms:
            printhist("all runs:", self.global_ham_hist, self.global_spam_hist)

        if options.save_histogram_pickles:
            for f, h in (('ham', self.global_ham_hist), ('spam', self.global_spam_hist)):
                fname = "%s_%shist.pik" % (options.pickle_basename, f)
                print "    saving %s histogram pickle to %s" %(f, fname)
                fp = file(fname, 'wb')
                pickle.dump(h, fp, 1)
                fp.close()

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

        if options.show_histograms:
            printhist("this pair:", local_ham_hist, local_spam_hist)
        self.trained_ham_hist += local_ham_hist
        self.trained_spam_hist += local_spam_hist
