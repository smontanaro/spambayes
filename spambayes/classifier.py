# This is an implementation of the Bayes-like spam classifier sketched
# by Paul Graham at <http://www.paulgraham.com/spam.html>.  We say
# "Bayes-like" because there are many ad hoc deviations from a
# "normal" Bayesian classifier.
#
# This implementation is due to Tim Peters et alia.

import time
from heapq import heapreplace
from sets import Set

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

HAMBIAS  = 2.0
SPAMBIAS = 1.0

# "And then there is the question of what probability to assign to words
# that occur in one corpus but not the other. Again by trial and error I
# chose .01 and .99.".  However, the code snippet clamps *all* probabilities
# into this range.  That's good in principle (IMO), because no finite amount
# of training data is good enough to justify probabilities of 0 or 1.  It
# may justify probabilities outside this range, though.
MIN_SPAMPROB = 0.01
MAX_SPAMPROB = 0.99

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
UNKNOWN_SPAMPROB = 0.5

# "I only consider words that occur more than five times in total".
# But the code snippet considers words that appear at least five times.
# This implementation follows the code rather than the explanation.
# (In addition, the count compared is after multiplying it with the
# appropriate bias factor.)
#
# XXX Reducing this to 1.0 (effectively not using it at all then) seemed to
# XXX give a sharp reduction in the f-n rate in a partial test run, while
# XXX adding a few mysterious f-ps.  Then boosting it to 2.0 appeared to
# XXX give an increase in the f-n rate in a partial test run.  This needs
# XXX deeper investigation.  Might also be good to develop a more general
# XXX concept of confidence:  MINCOUNT is a gross gimmick in that direction,
# XXX effectively saying we have no confidence in probabilities computed
# XXX from fewer than MINCOUNT instances, but unbounded confidence in
# XXX probabilities computed from at least MINCOUNT instances.
MINCOUNT = 5.0

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
MAX_DISCRIMINATORS = 16

PICKLE_VERSION = 1

class WordInfo(object):
    __slots__ = ('atime',     # when this record was last used by scoring(*)
                 'spamcount', # # of times word appears in spam
                 'hamcount',  # # of times word appears in non-spam
                 'killcount', # # of times this made it to spamprob()'s nbest
                 'spamprob',  # prob(spam | msg contains this word)
                )
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

    DEBUG = False

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

        if self.DEBUG:
            print "spamprob(%r)" % wordstream

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
            if self.DEBUG:
                print 'nbest P(%r) = %g' % (word, prob)
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
            hamcount = HAMBIAS * record.hamcount
            spamcount = SPAMBIAS * record.spamcount
            if hamcount + spamcount < MINCOUNT:
                prob = UNKNOWN_SPAMPROB
            else:
                hamratio = min(1.0, hamcount / nham)
                spamratio = min(1.0, spamcount / nspam)

                prob = spamratio / (hamratio + spamratio)
                if prob < MIN_SPAMPROB:
                    prob = MIN_SPAMPROB
                elif prob > MAX_SPAMPROB:
                    prob = MAX_SPAMPROB
            if record.spamprob != prob:
                record.spamprob = prob
                self.wordinfo[word] = record

        if self.DEBUG:
            print 'New probabilities:'
            for w, r in self.wordinfo.iteritems():
                print "P(%r) = %g" % (w, r.spamprob)

    def clearjunk(self, oldesttime, mincount=MINCOUNT):
        """Forget useless wordinfo records.  This can shrink the database size.

        A record for a word will be retained only if the word was accessed
        at or after oldesttime, or appeared at least mincount times in
        messages passed to learn().  mincount is optional, and defaults
        to the value an internal algorithm uses to decide that a word is so
        rare that it has no predictive value.
        """

        wordinfo = self.wordinfo
        mincount = float(mincount)
        tonuke = [w for w, r in wordinfo.iteritems()
                    if r.atime < oldesttime and
                       SPAMBIAS*r.spamcount + HAMBIAS*r.hamcount < mincount]
        for w in tonuke:
            if self.DEBUG:
                print "clearjunk removing word %r: %r" % (w, r)
            del wordinfo[w]

    def _add_msg(self, wordstream, is_spam):
        if self.DEBUG:
            print "_add_msg(%r, %r)" % (wordstream, is_spam)

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

            if self.DEBUG:
                print "new count for %r = %d" % (word,
                      is_spam and record.spamcount or record.hamcount)

    def _remove_msg(self, wordstream, is_spam):
        if self.DEBUG:
            print "_remove_msg(%r, %r)" % (wordstream, is_spam)

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
