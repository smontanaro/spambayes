#! /usr/bin/env python

"""Usage: %(program)s wordprobs.cdb Maildir Spamdir
"""

import sys
import os
import time
import signal
import socket
import email
from heapq import heapreplace
from sets import Set
import cdb
from tokenizer import tokenize
from classifier import MIN_SPAMPROB, MAX_SPAMPROB, UNKNOWN_SPAMPROB, \
    MAX_DISCRIMINATORS

program = sys.argv[0] # For usage(); referenced by docstring above

BLOCK_SIZE = 10000
SIZE_LIMIT = 5000000 # messages larger are not analyzed
SPAM_THRESHOLD = 0.9

def spamprob(wordprobs, wordstream):
    """Return best-guess probability that wordstream is spam.

    wordprobs is a CDB of word probabilities

    wordstream is an iterable object producing words.
    The return value is a float in [0.0, 1.0].
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
        for x in longer[:tokeep]:
            heapreplace(nbest, x)

    prob_product = inverse_prob_product = 1.0
    for distance, prob, word in nbest:
        if prob is None:    # it's one of the dummies nbest started with
            continue
        prob_product *= prob
        inverse_prob_product *= 1.0 - prob

    prob = prob_product / (prob_product + inverse_prob_product)
    return prob

def maketmp(dir):
    hostname = socket.gethostname()
    pid = os.getpid()
    fd = -1
    for x in xrange(200):
        filename = "%d.%d.%s" % (time.time(), pid, hostname)
        pathname = "%s/tmp/%s" % (dir, filename)
        try:
            fd = os.open(pathname, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0600)
        except IOError, exc:
            if exc[i] not in (errno.EINT, errno.EEXIST):
                raise
        else:
            break
        time.sleep(2)
    if fd == -1:
        raise SystemExit, "could not create a mail file"
    return (os.fdopen(fd, "wb"), pathname, filename)

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    if len(sys.argv) != 4:
        usage(2)

    wordprobfilename = sys.argv[1]
    hamdir = sys.argv[2]
    spamdir = sys.argv[3]

    signal.signal(signal.SIGALRM, lambda s: sys.exit(1))
    signal.alarm(24 * 60 * 60)

    # write message to temporary file (must be on same partition)
    tmpfile, pathname, filename = maketmp(hamdir)
    try:
        tmpfile.write(os.environ.get("DTLINE", "")) # delivered-to line
        bytes = 0
        blocks = []
        while 1:
            block = sys.stdin.read(BLOCK_SIZE)
            if not block:
                break
            bytes += len(block)
            if bytes < SIZE_LIMIT:
                blocks.append(block)
            tmpfile.write(block)
        tmpfile.close()

        if bytes < SIZE_LIMIT:
            msgdata = ''.join(blocks)
            del blocks
            msg = email.message_from_string(msgdata)
            del msgdata
            wordprobs = cdb.Cdb(open(wordprobfilename, 'rb'))
            prob = spamprob(wordprobs, tokenize(msg))
        else:
            prob = 0.0

        if prob > SPAM_THRESHOLD:
            os.rename(pathname, "%s/new/%s" % (spamdir, filename))
        else:
            os.rename(pathname, "%s/new/%s" % (hamdir, filename))
    except:
        os.unlink(pathname)
        raise

if __name__ == "__main__":
    main()
