#! /usr/bin/env python

"""Usage: %(program)s wordprobs.cdb
"""

import sys
import os
import email
from heapq import heapreplace
from sets import Set
from classifier import MIN_SPAMPROB, MAX_SPAMPROB, UNKNOWN_SPAMPROB, \
    MAX_DISCRIMINATORS
import cdb

program = sys.argv[0] # For usage(); referenced by docstring above

from tokenizer import tokenize

def spamprob(wordprobs, wordstream, evidence=False):
    """Return best-guess probability that wordstream is spam.

    wordprobs is a CDB of word probabilities

    wordstream is an iterable object producing words.
    The return value is a float in [0.0, 1.0].

    If optional arg evidence is True, the return value is a pair
        probability, evidence
    where evidence is a list of (word, probability) pairs.
    """

    # A priority queue to remember the MAX_DISCRIMINATORS best
    # probabilities, where "best" means largest distance from 0.5.
    # The tuples are (distance, prob, word).
    nbest = [(-1.0, None, None)] * MAX_DISCRIMINATORS
    smallest_best = -1.0

    mins = []   # all words w/ prob MIN_SPAMPROB
    maxs = []   # all words w/ prob MAX_SPAMPROB
    # Counting a unique word multiple times hurts, although counting one
    # at most two times had some benefit whan UNKNOWN_SPAMPROB was 0.2.
    # When that got boosted to 0.5, counting more than once became
    # counterproductive.
    for word in Set(wordstream):
        prob = float(wordprobs.get(word, UNKNOWN_SPAMPROB))
        distance = abs(prob - 0.5)
        if prob == MIN_SPAMPROB:
            mins.append((distance, prob, word))
        elif prob == MAX_SPAMPROB:
            maxs.append((distance, prob, word))
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
            heapreplace(nbest, (distance, prob, word))
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
        for dist, prob, word in shorter + longer[tokeep:]:
            if evidence:
                clues.append((word, prob))
        for x in longer[:tokeep]:
            heapreplace(nbest, x)

    prob_product = inverse_prob_product = 1.0
    for distance, prob, word in nbest:
        if prob is None:    # it's one of the dummies nbest started with
            continue
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

def formatclues(clues, sep="; "):
    """Format the clues into something readable."""
    return sep.join(["%r: %.2f" % (word, prob) for word, prob in clues])

def is_spam(wordprobs, input):
    """Filter (judge) a message"""
    msg = email.message_from_file(input)
    prob, clues = spamprob(wordprobs, tokenize(msg), True)
    #print "%.2f;" % prob, formatclues(clues)
    if prob < 0.9:
        return False
    else:
        return True

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    if len(sys.argv) != 2:
        usage(2)

    wordprobs = cdb.Cdb(open(sys.argv[1], 'rb'))
    if is_spam(wordprobs, sys.stdin):
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
