# This is an implementation of the Bayes-like spam classifier sketched
# by Paul Graham at <http://www.paulgraham.com/spam.html>.  We say
# "Bayes-like" because there are many ad hoc deviations from a
# "normal" Bayesian classifier.
#
# This implementation is due to Tim Peters et alia.

import time
from heapq import heapreplace
from sets import Set

from Options import options

# The count of each word in ham is artificially boosted by a factor of
# HAMBIAS, and similarly for SPAMBIAS.  Graham uses 2.0 and 1.0.  Final
# results are very sensitive to the HAMBIAS value.  On my 5x5 c.l.py
# test grid with 20,000 hams and 13,750 spams split into 5 pairs, then
# across all 20 test runs (for each pair, training on that pair then scoring
# against the other 4 pairs), and counting up all the unique msgs ever
# identified as false negative or positive, then compared to HAMBIAS 2.0,
#
# At HAMBIAS 1.0
#    total unique false positives goes up   by a factor of 7.6 ( 23 -> 174)
#    total unique false negatives goes down by a factor of 2   (337 -> 166)
#
# At HAMBIAS 3.0
#    total unique false positives goes down by a factor of 4.6 ( 23 ->   5)
#    total unique false negatives goes up   by a factor of 2.1 (337 -> 702)

HAMBIAS  = options.hambias  # 2.0
SPAMBIAS = options.spambias # 1.0

# "And then there is the question of what probability to assign to words
# that occur in one corpus but not the other. Again by trial and error I
# chose .01 and .99.".  However, the code snippet clamps *all* probabilities
# into this range.  That's good in principle (IMO), because no finite amount
# of training data is good enough to justify probabilities of 0 or 1.  It
# may justify probabilities outside this range, though.
MIN_SPAMPROB = options.min_spamprob # 0.01
MAX_SPAMPROB = options.max_spamprob # 0.99

# The spam probability assigned to words never seen before.  Graham used
# 0.2 here.  Neil Schemenauer reported that 0.5 seemed to work better.  In
# Tim's content-only tests (no headers), boosting to 0.5 cut the false
# negative rate by over 1/3.  The f-p rate increased, but there were so few
# f-ps that the increase wasn't statistically significant.  It also caught
# 13 more spams erroneously classified as ham.  By eyeball (and common
# sense <wink>), this has most effect on very short messages, where there
# simply aren't many high-value words.  A word with prob 0.5 is (in effect)
# completely ignored by spamprob(), in favor of *any* word with *any* prob
# differing from 0.5.  At 0.2, an unknown word favors ham at the expense
# of kicking out a word with a prob in (0.2, 0.8), and that seems dubious
# on the face of it.
UNKNOWN_SPAMPROB = options.unknown_spamprob # 0.5

# "I only consider words that occur more than five times in total".
# But the code snippet considers words that appear at least five times.
# This implementation follows the code rather than the explanation.
# (In addition, the count compared is after multiplying it with the
# appropriate bias factor.)
#
# Twist:  Graham used MINCOUNT=5.0 here.  I got rid of it:  in effect,
# given HAMBIAS=2.0, it meant we ignored a possibly perfectly good piece
# of spam evidence unless it appeared at least 5 times, and ditto for
# ham evidence unless it appeared at least 3 times.  That certainly does
# bias in favor of ham, but multiple distortions in favor of ham are
# multiple ways to get confused and trip up.  Here are the test results
# before and after, MINCOUNT=5.0 on the left, no MINCOUNT on the right;
# ham sets had 4000 msgs (so 0.025% is one msg), and spam sets 2750:
#
# false positive percentages
#     0.000  0.000  tied
#     0.000  0.000  tied
#     0.100  0.050  won    -50.00%
#     0.000  0.025  lost  +(was 0)
#     0.025  0.075  lost  +200.00%
#     0.025  0.000  won   -100.00%
#     0.100  0.100  tied
#     0.025  0.050  lost  +100.00%
#     0.025  0.025  tied
#     0.050  0.025  won    -50.00%
#     0.100  0.050  won    -50.00%
#     0.025  0.050  lost  +100.00%
#     0.025  0.050  lost  +100.00%
#     0.025  0.000  won   -100.00%
#     0.025  0.000  won   -100.00%
#     0.025  0.075  lost  +200.00%
#     0.025  0.025  tied
#     0.000  0.000  tied
#     0.025  0.025  tied
#     0.100  0.050  won    -50.00%
#
# won   7 times
# tied  7 times
# lost  6 times
#
# total unique fp went from 9 to 13
#
# false negative percentages
#     0.364  0.327  won    -10.16%
#     0.400  0.400  tied
#     0.400  0.327  won    -18.25%
#     0.909  0.691  won    -23.98%
#     0.836  0.545  won    -34.81%
#     0.618  0.291  won    -52.91%
#     0.291  0.218  won    -25.09%
#     1.018  0.654  won    -35.76%
#     0.982  0.364  won    -62.93%
#     0.727  0.291  won    -59.97%
#     0.800  0.327  won    -59.13%
#     1.163  0.691  won    -40.58%
#     0.764  0.582  won    -23.82%
#     0.473  0.291  won    -38.48%
#     0.473  0.364  won    -23.04%
#     0.727  0.436  won    -40.03%
#     0.655  0.436  won    -33.44%
#     0.509  0.218  won    -57.17%
#     0.545  0.291  won    -46.61%
#     0.509  0.254  won    -50.10%
#
# won  19 times
# tied  1 times
# lost  0 times
#
# total unique fn went from 168 to 106
#
# So dropping MINCOUNT was a huge win for the f-n rate, and a mixed bag
# for the f-p rate (but the f-p rate was so low compared to 4000 msgs that
# even the losses were barely significant).  In addition, dropping MINCOUNT
# had a larger good effect when using random training subsets of size 500;
# this makes intuitive sense, as with less training data it was harder to
# exceed the MINCOUNT threshold.
#
# Still, MINCOUNT seemed to be a gross approximation to *something* valuable:
# a strong clue appearing in 1,000 training msgs is certainly more trustworthy
# than an equally strong clue appearing in only 1 msg.  I'm almost certain it
# would pay to develop a way to take that into account when scoring.  In
# particular, there was a very specific new class of false positives
# introduced by dropping MINCOUNT:  some c.l.py msgs consisting mostly of
# Spanish or French.  The "high probability" spam clues were innocuous
# words like "puedo" and "como", that appeared in very rare Spanish and
# French spam too.  There has to be a more principled way to address this
# than the MINCOUNT hammer, and the test results clearly showed that MINCOUNT
# did more harm than good overall.


# The maximum number of words spamprob() pays attention to.  Graham had 15
# here.  If there are 8 indicators with spam probabilities near 1, and 7
# near 0, the math is such that the combined result is near 1.  Making this
# even gets away from that oddity (8 of each allows for graceful ties,
# which favor ham).
#
# XXX That should be revisited.  Stripping HTML tags from plain text msgs
# XXX later addressed some of the same problem cases.  The best value for
# XXX MAX_DISCRIMINATORS remains unknown, but increasing it a lot is known
# XXX to hurt.
# XXX Later:  tests after cutting this back to 15 showed no effect on the
# XXX f-p rate, and a tiny shift in the f-n rate (won 3 times, tied 8 times,
# XXX lost 9 times).  There isn't a significant difference, so leaving it
# XXX at 16.
#
# A twist:  When staring at failures, it wasn't unusual to see the top
# discriminators *all* have values of MIN_SPAMPROB and MAX_SPAMPROB.  The
# math is such that one MIN_SPAMPROB exactly cancels out one MAX_SPAMPROB,
# yielding no info at all.  Then whichever flavor of clue happened to reach
# MAX_DISCRIMINATORS//2 + 1 occurrences first determined the final outcome,
# based on almost no real evidence.
#
# So spamprob() was changed to save lists of *all* MIN_SPAMPROB and
# MAX_SPAMPROB clues.  If the number of those are equal, they're all ignored.
# Else the flavor with the smaller number of instances "cancels out" the
# same number of instances of the other flavor, and the remaining instances
# of the other flavor are fed into the probability computation.  This change
# was a pure win, lowering the false negative rate consistently, and it even
# managed to tickle a couple rare false positives into "not spam" terrority.
MAX_DISCRIMINATORS = options.max_discriminators # 16

PICKLE_VERSION = 1

class WordInfo(object):
    __slots__ = ('atime',     # when this record was last used by scoring(*)
                 'spamcount', # # of times word appears in spam
                 'hamcount',  # # of times word appears in non-spam
                 'killcount', # # of times this made it to spamprob()'s nbest
                 'spamprob',  # prob(spam | msg contains this word)
                )

    # Invariant:  For use in a classifier database, at least one of
    # spamcount and hamcount must be non-zero.
    #
    # (*)atime is the last access time, a UTC time.time() value.  It's the
    # most recent time this word was used by scoring (i.e., by spamprob(),
    # not by training via learn()); or, if the word has never been used by
    # scoring, the time the word record was created (i.e., by learn()).
    # One good criterion for identifying junk (word records that have no
    # value) is to delete words that haven't been used for a long time.
    # Perhaps they were typos, or unique identifiers, or relevant to a
    # once-hot topic or scam that's fallen out of favor.  Whatever, if
    # a word is no longer being used, it's just wasting space.

    def __init__(self, atime):
        self.atime = atime
        self.spamcount = self.hamcount = self.killcount = 0
        self.spamprob = None

    def __repr__(self):
        return "WordInfo%r" % repr((self.atime, self.spamcount,
                                    self.hamcount, self.killcount,
                                    self.spamprob))

    def __getstate__(self):
        return (self.atime, self.spamcount, self.hamcount, self.killcount,
                self.spamprob)

    def __setstate__(self, t):
        (self.atime, self.spamcount, self.hamcount, self.killcount,
         self.spamprob) = t

class GrahamBayes(object):
    __slots__ = ('wordinfo',  # map word to WordInfo record
                 'nspam',     # number of spam messages learn() has seen
                 'nham',      # number of non-spam messages learn() has seen
                )

    def __init__(self):
        self.wordinfo = {}
        self.nspam = self.nham = 0

    def __getstate__(self):
        return PICKLE_VERSION, self.wordinfo, self.nspam, self.nham

    def __setstate__(self, t):
        if t[0] != PICKLE_VERSION:
            raise ValueError("Can't unpickle -- version %s unknown" % t[0])
        self.wordinfo, self.nspam, self.nham = t[1:]

    def spamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        # A priority queue to remember the MAX_DISCRIMINATORS best
        # probabilities, where "best" means largest distance from 0.5.
        # The tuples are (distance, prob, word, wordinfo[word]).
        nbest = [(-1.0, None, None, None)] * MAX_DISCRIMINATORS
        smallest_best = -1.0

        wordinfoget = self.wordinfo.get
        now = time.time()
        mins = []   # all words w/ prob MIN_SPAMPROB
        maxs = []   # all words w/ prob MAX_SPAMPROB
        # Counting a unique word multiple times hurts, although counting one
        # at most two times had some benefit whan UNKNOWN_SPAMPROB was 0.2.
        # When that got boosted to 0.5, counting more than once became
        # counterproductive.
        for word in Set(wordstream):
            record = wordinfoget(word)
            if record is None:
                prob = UNKNOWN_SPAMPROB
            else:
                record.atime = now
                prob = record.spamprob

            distance = abs(prob - 0.5)
            if prob == MIN_SPAMPROB:
                mins.append((distance, prob, word, record))
            elif prob == MAX_SPAMPROB:
                maxs.append((distance, prob, word, record))
            elif distance > smallest_best:
                # Subtle:  we didn't use ">" instead of ">=" just to save
                # calls to heapreplace().  The real intent is that if
                # there are many equally strong indicators throughout the
                # message, we want to favor the ones that appear earliest:
                # it's expected that spam headers will often have smoking
                # guns, and, even when not, spam has to grab your attention
                # early (& note that when spammers generate large blocks of
                # random gibberish to throw off exact-match filters, it's
                # always at the end of the msg -- if they put it at the
                # start, *nobody* would read the msg).
                heapreplace(nbest, (distance, prob, word, record))
                smallest_best = nbest[0][0]

        # Compute the probability.  Note:  This is what Graham's code did,
        # but it's dubious for reasons explained in great detail on Python-
        # Dev:  it's missing P(spam) and P(not-spam) adjustments that
        # straightforward Bayesian analysis says should be here.  It's
        # unclear how much it matters, though, as the omissions here seem
        # to tend in part to cancel out distortions introduced earlier by
        # HAMBIAS.  Experiments will decide the issue.
        clues = []

        # First cancel out competing extreme clues (see comment block at
        # MAX_DISCRIMINATORS declaration -- this is a twist on Graham).
        if mins or maxs:
            if len(mins) < len(maxs):
                shorter, longer = mins, maxs
            else:
                shorter, longer = maxs, mins
            tokeep = min(len(longer) - len(shorter), MAX_DISCRIMINATORS)
            # They're all good clues, but we're only going to feed the tokeep
            # initial clues from the longer list into the probability
            # computation.
            for dist, prob, word, record in shorter + longer[tokeep:]:
                record.killcount += 1
                if evidence:
                    clues.append((word, prob))
            for x in longer[:tokeep]:
                heapreplace(nbest, x)

        if options.use_robinson_probability:
            # This combination method is due to Gary Robinson.
            # http://radio.weblogs.com/0101454/stories/2002/09/16/spamDetection.html
            # In preliminary tests, it did just as well as Graham's scheme,
            # but creates a definite "middle ground" around 0.5 where false
            # negatives and false positives can actually found in non-trivial
            # number.
            P = Q = 1.0
            num_clues = 0
            for distance, prob, word, record in nbest:
                if prob is None:    # it's one of the dummies nbest started with
                    continue
                if record is not None:  # else wordinfo doesn't know about it
                    record.killcount += 1
                if evidence:
                    clues.append((word, prob))
                num_clues += 1
                P *= 1.0 - prob
                Q *= prob

            if num_clues:
                P = 1.0 - P**(1./num_clues)
                Q = 1.0 - Q**(1./num_clues)
                prob = (P-Q)/(P+Q)  # in -1 .. 1
                prob = 0.5 + prob/2 # shift to 0 .. 1
            else:
                prob = 0.5
        else:
            prob_product = inverse_prob_product = 1.0
            for distance, prob, word, record in nbest:
                if prob is None:    # it's one of the dummies nbest started with
                    continue
                if record is not None:  # else wordinfo doesn't know about it
                    record.killcount += 1
                if evidence:
                    clues.append((word, prob))
                prob_product *= prob
                inverse_prob_product *= 1.0 - prob

            prob = prob_product / (prob_product + inverse_prob_product)

        if evidence:
            clues.sort(lambda a, b: cmp(a[1], b[1]))
            return prob, clues
        else:
            return prob

    # The same as spamprob(), except uses a corrected probability computation
    # accounting for P(spam) and P(not-spam).  Since my training corpora had
    # a ham/spam ratio of 4000/2750, I'm in a good position to test this.
    # Using xspamprob() clearly made a major reduction in the false negative
    # rate, cutting it in half on some runs (this is after the f-n rate had
    # already been cut by a factor of 5 via other refinements).  It also
    # uncovered two more very brief spams hiding in the ham corpora.
    #
    # OTOH, the # of fps increased.  Especially vulnerable are extremely
    # short msgs of the "subscribe me"/"unsubscribe me" variety (while these
    # don't belong on a mailing list, they're not spam), and brief reasonable
    # msgs that simply don't have much evidence (to the human eye) to go on.
    # These were boderline before, and it's easy to push them over the edge.
    # For example, one f-p had subject
    #
    #     Any Interest in EDIFACT Parser/Generator?
    #
    # and the body just
    #
    #     Just curious.
    #     --jim
    #
    # "Interest" in the subject line had spam prob 0.99, "curious." 0.01,
    # and nothing else was strong.  Since my ham/spam ratio is bigger than
    # 1, any clue favoring spam favors spam more strongly under xspamprob()
    # than under spamprob().
    #
    # XXX Somewhat like spamprob(), learn() also computes probabilities as
    # XXX if the # of hams and spams were the same.  If that were also
    # XXX fiddled to take nham and nspam into account (nb:  I realize it
    # XXX already *looks* like it does -- but it doesn't), it would reduce
    # XXX the spam probabilities in my test run, and *perhaps* xspamprob
    # XXX wouldn't have such bad effect on the f-p story.
    #
    # Here are the comparative stats, with spamprob() in the left column and
    # xspamprob() in the right, across 20 runs:
    #
    #    false positive percentages
    #        0.000  0.000  tied
    #        0.000  0.050  lost
    #        0.050  0.100  lost
    #        0.000  0.075  lost
    #        0.025  0.050  lost
    #        0.025  0.100  lost
    #        0.050  0.150  lost
    #        0.025  0.050  lost
    #        0.025  0.050  lost
    #        0.000  0.050  lost
    #        0.075  0.150  lost
    #        0.050  0.075  lost
    #        0.025  0.050  lost
    #        0.000  0.050  lost
    #        0.050  0.125  lost
    #        0.025  0.075  lost
    #        0.025  0.025  tied
    #        0.000  0.025  lost
    #        0.025  0.100  lost
    #        0.050  0.150  lost
    #
    #    won   0 times
    #    tied  2 times
    #    lost 18 times
    #
    #    total unique fp went from 8 to 30
    #
    #    false negative percentages
    #        0.945  0.473  won
    #        0.836  0.582  won
    #        1.200  0.618  won
    #        1.418  0.836  won
    #        1.455  0.836  won
    #        1.091  0.691  won
    #        1.091  0.618  won
    #        1.236  0.691  won
    #        1.564  1.018  won
    #        1.236  0.618  won
    #        1.563  0.981  won
    #        1.563  0.800  won
    #        1.236  0.618  won
    #        0.836  0.400  won
    #        0.873  0.400  won
    #        1.236  0.545  won
    #        1.273  0.691  won
    #        1.018  0.327  won
    #        1.091  0.473  won
    #        1.490  0.618  won
    #
    #    won  20 times
    #    tied  0 times
    #    lost  0 times
    #
    #    total unique fn went from 292 to 162
    #
    # XXX This needs to be updated to incorporate the "cancel out competing
    # XXX extreme clues" twist.
    def xspamprob(self, wordstream, evidence=False):
        """Return best-guess probability that wordstream is spam.

        wordstream is an iterable object producing words.
        The return value is a float in [0.0, 1.0].

        If optional arg evidence is True, the return value is a pair
            probability, evidence
        where evidence is a list of (word, probability) pairs.
        """

        # A priority queue to remember the MAX_DISCRIMINATORS best
        # probabilities, where "best" means largest distance from 0.5.
        # The tuples are (distance, prob, word, wordinfo[word]).
        nbest = [(-1.0, None, None, None)] * MAX_DISCRIMINATORS
        smallest_best = -1.0

        # Counting a unique word multiple times hurts, although counting one
        # at most two times had some benefit whan UNKNOWN_SPAMPROB was 0.2.
        # When that got boosted to 0.5, counting more than once became
        # counterproductive.
        unique_words = {}

        wordinfoget = self.wordinfo.get
        now = time.time()

        for word in wordstream:
            if word in unique_words:
                continue
            unique_words[word] = 1

            record = wordinfoget(word)
            if record is None:
                prob = UNKNOWN_SPAMPROB
            else:
                record.atime = now
                prob = record.spamprob

            distance = abs(prob - 0.5)
            if distance > smallest_best:
                # Subtle:  we didn't use ">" instead of ">=" just to save
                # calls to heapreplace().  The real intent is that if
                # there are many equally strong indicators throughout the
                # message, we want to favor the ones that appear earliest:
                # it's expected that spam headers will often have smoking
                # guns, and, even when not, spam has to grab your attention
                # early (& note that when spammers generate large blocks of
                # random gibberish to throw off exact-match filters, it's
                # always at the end of the msg -- if they put it at the
                # start, *nobody* would read the msg).
                heapreplace(nbest, (distance, prob, word, record))
                smallest_best = nbest[0][0]

        # Compute the probability.
        if evidence:
            clues = []
        sp = float(self.nspam) / (self.nham + self.nspam)
        hp = 1.0 - sp
        prob_product = sp
        inverse_prob_product = hp
        for distance, prob, word, record in nbest:
            if prob is None:    # it's one of the dummies nbest started with
                continue
            if record is not None:  # else wordinfo doesn't know about it
                record.killcount += 1
            if evidence:
                clues.append((word, prob))
            prob_product *= prob / sp
            inverse_prob_product *= (1.0 - prob) / hp

        prob = prob_product / (prob_product + inverse_prob_product)
        if evidence:
            return prob, clues
        else:
            return prob


    def learn(self, wordstream, is_spam, update_probabilities=True):
        """Teach the classifier by example.

        wordstream is a word stream representing a message.  If is_spam is
        True, you're telling the classifier this message is definitely spam,
        else that it's definitely not spam.

        If optional arg update_probabilities is False (the default is True),
        don't update word probabilities.  Updating them is expensive, and if
        you're going to pass many messages to learn(), it's more efficient
        to pass False here and call update_probabilities() once when you're
        done -- or to call learn() with update_probabilities=True when
        passing the last new example.  The important thing is that the
        probabilities get updated before calling spamprob() again.
        """

        self._add_msg(wordstream, is_spam)
        if update_probabilities:
            self.update_probabilities()

    def unlearn(self, wordstream, is_spam, update_probabilities=True):
        """In case of pilot error, call unlearn ASAP after screwing up.

        Pass the same arguments you passed to learn().
        """

        self._remove_msg(wordstream, is_spam)
        if update_probabilities:
            self.update_probabilities()

    def update_probabilities(self):
        """Update the word probabilities in the spam database.

        This computes a new probability for every word in the database,
        so can be expensive.  learn() and unlearn() update the probabilities
        each time by default.  Thay have an optional argument that allows
        to skip this step when feeding in many messages, and in that case
        you should call update_probabilities() after feeding the last
        message and before calling spamprob().
        """

        nham = float(self.nham or 1)
        nspam = float(self.nspam or 1)
        for word,record in self.wordinfo.iteritems():
            # Compute prob(msg is spam | msg contains word).
            hamcount = min(HAMBIAS * record.hamcount, nham)
            spamcount = min(SPAMBIAS * record.spamcount, nspam)
            hamratio = hamcount / nham
            spamratio = spamcount / nspam

            prob = spamratio / (hamratio + spamratio)
            if prob < MIN_SPAMPROB:
                prob = MIN_SPAMPROB
            elif prob > MAX_SPAMPROB:
                prob = MAX_SPAMPROB

            if record.spamprob != prob:
                record.spamprob = prob
                # The next seemingly pointless line appears to be a hack
                # to allow a persistent db to realize the record has changed.
                self.wordinfo[word] = record

    def clearjunk(self, oldesttime):
        """Forget useless wordinfo records.  This can shrink the database size.

        A record for a word will be retained only if the word was accessed
        at or after oldesttime.
        """

        wordinfo = self.wordinfo
        mincount = float(mincount)
        tonuke = [w for w, r in wordinfo.iteritems() if r.atime < oldesttime]
        for w in tonuke:
            del wordinfo[w]

    def _add_msg(self, wordstream, is_spam):
        if is_spam:
            self.nspam += 1
        else:
            self.nham += 1

        wordinfo = self.wordinfo
        wordinfoget = wordinfo.get
        now = time.time()
        for word in wordstream:
            record = wordinfoget(word)
            if record is None:
                record = wordinfo[word] = WordInfo(now)

            if is_spam:
                record.spamcount += 1
            else:
                record.hamcount += 1
            wordinfo[word] = record

    def _remove_msg(self, wordstream, is_spam):
        if is_spam:
            if self.nspam <= 0:
                raise ValueError("spam count would go negative!")
            self.nspam -= 1
        else:
            if self.nham <= 0:
                raise ValueError("non-spam count would go negative!")
            self.nham -= 1

        wordinfoget = self.wordinfo.get
        for word in wordstream:
            record = wordinfoget(word)
            if record is not None:
                if is_spam:
                    if record.spamcount > 0:
                        record.spamcount -= 1
                else:
                    if record.hamcount > 0:
                        record.hamcount -= 1
                if record.hamcount == 0 == record.spamcount:
                    del self.wordinfo[word]
