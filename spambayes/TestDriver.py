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
from Histogram import Hist

def printhist(tag, ham, spam, nbuckets=options.nbuckets):
    print
    print "-> <stat> Ham scores for", tag,
    ham.display(nbuckets)

    print
    print "-> <stat> Spam scores for", tag,
    spam.display(nbuckets)

    if not options.compute_best_cutoffs_from_histograms:
        return
    if ham.n == 0 or spam.n == 0:
        return

    # Figure out "the best" spam cutoff point, meaning the one that minimizes
    # the total number of misclassified msgs (other definitions are
    # certainly possible!).

    # At cutoff 0, everything is called spam, so there are no false negatives,
    # and every ham is a false positive.
    assert ham.nbuckets == spam.nbuckets
    fpw = options.best_cutoff_fp_weight
    fp = ham.n
    fn = 0
    best_total = fpw * fp + fn
    bests = [(0, fp, fn)]
    for i in range(nbuckets):
        # When moving the cutoff beyond bucket i, the ham in bucket i
        # are redeemed, and the spam in bucket i become false negatives.
        fp -= ham.buckets[i]
        fn += spam.buckets[i]
        total = fpw * fp + fn
        if total <= best_total:
            if total < best_total:
                best_total = total
                bests = []
            bests.append((i+1, fp, fn))
    assert fp == 0
    assert fn == spam.n

    i, fp, fn = bests.pop(0)
    print '-> best cutoff for', tag, float(i) / nbuckets
    print '->     with weighted total %g*%d fp + %d fn = %g' % (
          fpw, fp, fn, best_total)
    print '->     fp rate %.3g%%  fn rate %.3g%%' % (
          fp * 1e2 / ham.n, fn * 1e2 / spam.n)
    for i, fp, fn in bests:
        print ('->     matched at %g with %d fp & %d fn; '
               'fp rate %.3g%%; fn rate %.3g%%' % (
               float(i) / ham.nbuckets, fp, fn,
               fp * 1e2 / ham.n, fn * 1e2 / spam.n))


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
        self.global_ham_hist = Hist()
        self.global_spam_hist = Hist()
        self.ntimes_finishtest_called = 0
        self.new_classifier()

    def new_classifier(self):
        c = self.classifier = classifier.Bayes()
        self.tester = Tester.Test(c)
        self.trained_ham_hist = Hist()
        self.trained_spam_hist = Hist()

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
        self.trained_ham_hist = Hist()
        self.trained_spam_hist = Hist()

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
            for f, h in (('ham', self.global_ham_hist),
                         ('spam', self.global_spam_hist)):
                fname = "%s_%shist.pik" % (options.pickle_basename, f)
                print "    saving %s histogram pickle to %s" %(f, fname)
                fp = file(fname, 'wb')
                pickle.dump(h, fp, 1)
                fp.close()

    def test(self, ham, spam):
        c = self.classifier
        t = self.tester
        local_ham_hist = Hist()
        local_spam_hist = Hist()

        def new_ham(msg, prob, lo=options.show_ham_lo,
                               hi=options.show_ham_hi):
            local_ham_hist.add(prob * 100.0)
            if lo <= prob <= hi:
                print
                print "Ham with prob =", prob
                prob, clues = c.spamprob(msg, True)
                printmsg(msg, prob, clues)

        def new_spam(msg, prob, lo=options.show_spam_lo,
                                hi=options.show_spam_hi):
            local_spam_hist.add(prob * 100.0)
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
