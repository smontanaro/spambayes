#! /usr/bin/env python
# An implementation of a Bayes-like spam classifier.
#
# Paul Graham's original description:
#
#     http://www.paulgraham.com/spam.html
#
# A highly fiddled version of that can be retrieved from our CVS repository,
# via tag Last-Graham.  This made many demonstrated improvements in error
# rates over Paul's original description.
#
# This code implements Gary Robinson's suggestions, the core of which are
# well explained on his webpage:
#
#    http://radio.weblogs.com/0101454/stories/2002/09/16/spamDetection.html
#
# This is theoretically cleaner, and in testing has performed at least as
# well as our highly tuned Graham scheme did, often slightly better, and
# sometimes much better.  It also has "a middle ground", which people like:
# the scores under Paul's scheme were almost always very near 0 or very near
# 1, whether or not the classification was correct.  The false positives
# and false negatives under Gary's basic scheme (use_gary_combining) generally
# score in a narrow range around the corpus's best spam_cutoff value.
# However, it doesn't appear possible to guess the best spam_cutoff value in
# advance, and it's touchy.
#
# The chi-combining scheme used by default here gets closer to the theoretical
# basis of Gary's combining scheme, and does give extreme scores, but also
# has a very useful middle ground (small # of msgs spread across a large range
# of scores, and good cutoff values aren't touchy).
#
# This implementation is due to Tim Peters et alia.

import math
try:
    from sets import Set
except ImportError:
    from spambayes.compatsets import Set

from spambayes.Options import options
from spambayes.chi2 import chi2Q

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


LN2 = math.log(2)       # used frequently by chi-combining

PICKLE_VERSION = 5

class WordInfo(object):
    # Invariant:  For use in a classifier database, at least one of
    # spamcount and hamcount must be non-zero.

    def __init__(self):
        self.__setstate__((0, 0))

    def __repr__(self):
        return "WordInfo%r" % repr((self.spamcount,
                                    self.hamcount))

    def __getstate__(self):
        return (self.spamcount,
                self.hamcount)

    def __setstate__(self, t):
        (self.spamcount, self.hamcount) = t


class Classifier:
    # Defining __slots__ here made Jeremy's life needlessly difficult when
    # trying to hook this all up to ZODB as a persistent object.  There's
    # no space benefit worth getting from slots in this class; slots were
    # used solely to help catch errors earlier, when this code was changing
    # rapidly.

    #__slots__ = ('wordinfo',  # map word to WordInfo record
    #             'nspam',     # number of spam messages learn() has seen
    #             'nham',      # number of non-spam messages learn() has seen
    #            )

    # allow a subclass to use a different class for WordInfo
    WordInfoClass = WordInfo

    def __init__(self):
        self.wordinfo = {}
        self.probcache = {}
        self.nspam = self.nham = 0

    def __getstate__(self):
        return (PICKLE_VERSION, self.wordinfo, self.nspam, self.nham)

    def __setstate__(self, t):
        if t[0] != PICKLE_VERSION:
            raise ValueError("Can't unpickle -- version %s unknown" % t[0])
        (self.wordinfo, self.nspam, self.nham) = t[1:]
        self.probcache = {}

    # spamprob() implementations.  One of the following is aliased to
    # spamprob, depending on option settings.

    def gary_spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import frexp

        # This combination method is due to Gary Robinson; see
        # http://radio.weblogs.com/0101454/stories/2002/09/16/spamDetection.html

        # The real P = this P times 2**Pexp.  Likewise for Q.  We're
        # simulating unbounded dynamic float range by hand.  If this pans
        # out, *maybe* we should store logarithms in the database instead
        # and just add them here.  But I like keeping raw counts in the
        # database (they're easy to understand, manipulate and combine),
        # and there's no evidence that this simulation is a significant
        # expense.
        P = Q = 1.0
        Pexp = Qexp = 0
        clues = self._getclues(wordstream)
        for prob, word, record in clues:
            P *= 1.0 - prob
            Q *= prob
            if P < 1e-200:  # move back into range
                P, e = frexp(P)
                Pexp += e
            if Q < 1e-200:  # move back into range
                Q, e = frexp(Q)
                Qexp += e

        P, e = frexp(P)
        Pexp += e
        Q, e = frexp(Q)
        Qexp += e

        num_clues = len(clues)
        if num_clues:
            #P = 1.0 - P**(1./num_clues)
            #Q = 1.0 - Q**(1./num_clues)
            #
            # (x*2**e)**n = x**n * 2**(e*n)
            n = 1.0 / num_clues
            P = 1.0 - P**n * 2.0**(Pexp * n)
            Q = 1.0 - Q**n * 2.0**(Qexp * n)

            # (P-Q)/(P+Q) is in -1 .. 1; scaling into 0 .. 1 gives
            # ((P-Q)/(P+Q)+1)/2 =
            # ((P-Q+P-Q)/(P+Q)/2 =
            # (2*P/(P+Q)/2 =
            # P/(P+Q)
            prob = P/(P+Q)
        else:
            prob = 0.5

        if evidence:
            clues = [(w, p) for p, w, r in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            return prob, clues
        else:
            return prob

    if options.use_gary_combining:
        spamprob = gary_spamprob

    # Across vectors of length n, containing random uniformly-distributed
    # probabilities, -2*sum(ln(p_i)) follows the chi-squared distribution
    # with 2*n degrees of freedom.  This has been proven (in some
    # appropriate sense) to be the most sensitive possible test for
    # rejecting the hypothesis that a vector of probabilities is uniformly
    # distributed.  Gary Robinson's original scheme was monotonic *with*
    # this test, but skipped the details.  Turns out that getting closer
    # to the theoretical roots gives a much sharper classification, with
    # a very small (in # of msgs), but also very broad (in range of scores),
    # "middle ground", where most of the mistakes live.  In particular,
    # this scheme seems immune to all forms of "cancellation disease":  if
    # there are many strong ham *and* spam clues, this reliably scores
    # close to 0.5.  Most other schemes are extremely certain then -- and
    # often wrong.
    def chi2_spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        from math import frexp, log as ln

        # We compute two chi-squared statistics, one for ham and one for
        # spam.  The sum-of-the-logs business is more sensitive to probs
        # near 0 than to probs near 1, so the spam measure uses 1-p (so
        # that high-spamprob words have greatest effect), and the ham
        # measure uses p directly (so that lo-spamprob words have greatest
        # effect).
        #
        # For optimization, sum-of-logs == log-of-product, and f.p.
        # multiplication is a lot cheaper than calling ln().  It's easy
        # to underflow to 0.0, though, so we simulate unbounded dynamic
        # range via frexp.  The real product H = this H * 2**Hexp, and
        # likewise the real product S = this S * 2**Sexp.
        H = S = 1.0
        Hexp = Sexp = 0

        clues = self._getclues(wordstream)
        for prob, word, record in clues:
            S *= 1.0 - prob
            H *= prob
            if S < 1e-200:  # prevent underflow
                S, e = frexp(S)
                Sexp += e
            if H < 1e-200:  # prevent underflow
                H, e = frexp(H)
                Hexp += e

        # Compute the natural log of the product = sum of the logs:
        # ln(x * 2**i) = ln(x) + i * ln(2).
        S = ln(S) + Sexp * LN2
        H = ln(H) + Hexp * LN2

        n = len(clues)
        if n:
            S = 1.0 - chi2Q(-2.0 * S, 2*n)
            H = 1.0 - chi2Q(-2.0 * H, 2*n)

            # How to combine these into a single spam score?  We originally
            # used (S-H)/(S+H) scaled into [0., 1.], which equals S/(S+H).  A
            # systematic problem is that we could end up being near-certain
            # a thing was (for example) spam, even if S was small, provided
            # that H was much smaller.
            # Rob Hooft stared at these problems and invented the measure
            # we use now, the simpler S-H, scaled into [0., 1.].
            prob = (S-H + 1.0) / 2.0
        else:
            prob = 0.5

        if evidence:
            clues = [(w, p) for p, w, r in clues]
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            clues.insert(0, ('*S*', S))
            clues.insert(0, ('*H*', H))
            return prob, clues
        else:
            return prob

    if options.use_chi_squared_combining:
        spamprob = chi2_spamprob

    def learn(self, wordstream, is_spam):
        """Teach the classifier by example.

        wordstream is a word stream representing a message.  If is_spam is
        True, you're telling the classifier this message is definitely spam,
        else that it's definitely not spam.

        """

        self._add_msg(wordstream, is_spam)

    def unlearn(self, wordstream, is_spam):
        """In case of pilot error, call unlearn ASAP after screwing up.

        Pass the same arguments you passed to learn().
        """
        self._remove_msg(wordstream, is_spam)

    def probability(self, record):
        """Compute, store, and return prob(msg is spam | msg contains word).

        This is the Graham calculation, but stripped of biases, and
        stripped of clamping into 0.01 thru 0.99.  The Bayesian
        adjustment following keeps them in a sane range, and one
        that naturally grows the more evidence there is to back up
        a probability.
        """

        spamcount = record.spamcount
        hamcount = record.hamcount

        # Try the cache first
        try:
            return self.probcache[spamcount][hamcount]
        except KeyError:
            pass

        nham = float(self.nham or 1)
        nspam = float(self.nspam or 1)

        assert hamcount <= nham
        hamratio = hamcount / nham

        assert spamcount <= nspam
        spamratio = spamcount / nspam

        prob = spamratio / (hamratio + spamratio)

        if options.experimental_ham_spam_imbalance_adjustment:
            spam2ham = min(nspam / nham, 1.0)
            ham2spam = min(nham / nspam, 1.0)
        else:
            spam2ham = ham2spam = 1.0

        S = options.unknown_word_strength
        StimesX = S * options.unknown_word_prob


        # Now do Robinson's Bayesian adjustment.
        #
        #         s*x + n*p(w)
        # f(w) = --------------
        #           s + n
        #
        # I find this easier to reason about like so (equivalent when
        # s != 0):
        #
        #        x - p
        #  p +  -------
        #       1 + n/s
        #
        # IOW, it moves p a fraction of the distance from p to x, and
        # less so the larger n is, or the smaller s is.

        # Experimental:
        # Picking a good value for n is interesting:  how much empirical
        # evidence do we really have?  If nham == nspam,
        # hamcount + spamcount makes a lot of sense, and the code here
        # does that by default.
        # But if, e.g., nham is much larger than nspam, p(w) can get a
        # lot closer to 0.0 than it can get to 1.0.  That in turn makes
        # strong ham words (high hamcount) much stronger than strong
        # spam words (high spamcount), and that makes the accidental
        # appearance of a strong ham word in spam much more damaging than
        # the accidental appearance of a strong spam word in ham.
        # So we don't give hamcount full credit when nham > nspam (or
        # spamcount when nspam > nham):  instead we knock hamcount down
        # to what it would have been had nham been equal to nspam.  IOW,
        # we multiply hamcount by nspam/nham when nspam < nham; or, IOOW,
        # we don't "believe" any count to an extent more than
        # min(nspam, nham) justifies.

        n = hamcount * spam2ham  +  spamcount * ham2spam
        prob = (StimesX + n * prob) / (S + n)

        # Update the cache
        try:
            self.probcache[spamcount][hamcount] = prob
        except KeyError:
            self.probcache[spamcount] = {hamcount: prob}

        return prob

    # NOTE:  Graham's scheme had a strange asymmetry:  when a word appeared
    # n>1 times in a single message, training added n to the word's hamcount
    # or spamcount, but predicting scored words only once.  Tests showed
    # that adding only 1 in training, or scoring more than once when
    # predicting, hurt under the Graham scheme.
    # This isn't so under Robinson's scheme, though:  results improve
    # if training also counts a word only once.  The mean ham score decreases
    # significantly and consistently, ham score variance decreases likewise,
    # mean spam score decreases (but less than mean ham score, so the spread
    # increases), and spam score variance increases.
    # I (Tim) speculate that adding n times under the Graham scheme helped
    # because it acted against the various ham biases, giving frequently
    # repeated spam words (like "Viagra") a quick ramp-up in spamprob; else,
    # adding only once in training, a word like that was simply ignored until
    # it appeared in 5 distinct training spams.  Without the ham-favoring
    # biases, though, and never ignoring words, counting n times introduces
    # a subtle and unhelpful bias.
    # There does appear to be some useful info in how many times a word
    # appears in a msg, but distorting spamprob doesn't appear a correct way
    # to exploit it.
    def _add_msg(self, wordstream, is_spam):
        # I think the string stuff is hiding the cause of the db ham/spam
        # count problem, so remove it for now.
        self.probcache = {}    # nuke the prob cache
        if is_spam:
            #self.nspam = int(self.nspam) + 1  # account for string nspam
            self.nspam += 1
        else:
            #self.nham = int(self.nham) + 1   # account for string nham
            self.nham += 1

        for word in Set(wordstream):
            record = self._wordinfoget(word)
            if record is None:
                record = self.WordInfoClass()

            if is_spam:
                record.spamcount += 1
            else:
                record.hamcount += 1

            self._wordinfoset(word, record)


    def _remove_msg(self, wordstream, is_spam):
        self.probcache = {}    # nuke the prob cache
        if is_spam:
            if self.nspam <= 0:
                raise ValueError("spam count would go negative!")
            self.nspam -= 1
        else:
            if self.nham <= 0:
                raise ValueError("non-spam count would go negative!")
            self.nham -= 1

        for word in Set(wordstream):
            record = self._wordinfoget(word)
            if record is not None:
                if is_spam:
                    if record.spamcount > 0:
                        record.spamcount -= 1
                else:
                    if record.hamcount > 0:
                        record.hamcount -= 1
                if record.hamcount == 0 == record.spamcount:
                    self._wordinfodel(word)
                else:
                    self._wordinfoset(word, record)

    def _getclues(self, wordstream):
        mindist = options.minimum_prob_strength
        unknown = options.unknown_word_prob

        clues = []  # (distance, prob, word, record) tuples
        pushclue = clues.append

        for word in Set(wordstream):
            record = self._wordinfoget(word)
            if record is None:
                prob = unknown
            else:
                prob = self.probability(record)
            distance = abs(prob - 0.5)
            if distance >= mindist:
                pushclue((distance, prob, word, record))

        clues.sort()
        if len(clues) > options.max_discriminators:
            del clues[0 : -options.max_discriminators]
        # Return (prob, word, record).
        return [t[1:] for t in clues]

    def _wordinfoget(self, word):
        return self.wordinfo.get(word)

    def _wordinfoset(self, word, record):
        self.wordinfo[word] = record

    def _wordinfodel(self, word):
        del self.wordinfo[word]


Bayes = Classifier
