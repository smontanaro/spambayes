#! /usr/bin/env python
# At the moment, this requires Python 2.3 from CVS (heapq, Set, enumerate).

# A driver for N-fold cross validation.

"""Usage: %(program)s [options] -n nsets

Where:
    -h
        Show usage and exit.
    -n int
        Number of Set directories (Data/Spam/Set1, ... and Data/Ham/Set1, ...).
        This is required.

If you only want to use some of the messages in each set,

    --ham-keep int
        The maximum number of msgs to use from each Ham set.  The msgs are
        chosen randomly.  See also the -s option.

    --spam-keep int
        The maximum number of msgs to use from each Spam set.  The msgs are
        chosen randomly.  See also the -s option.

    -s int
        A seed for the random number generator.  Has no effect unless
        at least on of {--ham-keep, --spam-keep} is specified.  If -s
        isn't specifed, the seed is taken from current time.

In addition, an attempt is made to merge bayescustomize.ini into the options.
If that exists, it can be used to change the settings in Options.options.
"""

from __future__ import generators

import os
import sys
import random

from Options import options
from tokenizer import tokenize
import TestDriver

HAMKEEP  = None
SPAMKEEP = None
SEED = random.randrange(2000000000)

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class Msg(object):
    __slots__ = 'tag', 'guts'

    def __init__(self, dir, name):
        path = dir + "/" + name
        self.tag = path
        f = open(path, 'rb')
        self.guts = f.read()
        f.close()

    def __iter__(self):
        return tokenize(self.guts)

    # Compare msgs by their paths; this is appropriate for sets of msgs.
    def __hash__(self):
        return hash(self.tag)

    def __eq__(self, other):
        return self.tag == other.tag

    def __str__(self):
        return self.guts

class MsgStream(object):
    __slots__ = 'tag', 'directories', 'keep'

    def __init__(self, tag, directories, keep=None):
        self.tag = tag
        self.directories = directories
        self.keep = keep

    def __str__(self):
        return self.tag

    def produce(self):
        if self.keep is None:
            for directory in self.directories:
                for fname in os.listdir(directory):
                    yield Msg(directory, fname)
            return
        # We only want part of the msgs.  Shuffle each directory list, but
        # in such a way that we'll get the same result each time this is
        # called on the same directory list.
        for directory in self.directories:
            all = os.listdir(directory)
            random.seed(hash(max(all)) ^ SEED) # reproducible across calls
            random.shuffle(all)
            del all[self.keep:]
            all.sort()  # seems to speed access on Win98!
            for fname in all:
                yield Msg(directory, fname)

    def __iter__(self):
        return self.produce()

class HamStream(MsgStream):
    def __init__(self, tag, directories):
        MsgStream.__init__(self, tag, directories, HAMKEEP)

class SpamStream(MsgStream):
    def __init__(self, tag, directories):
        MsgStream.__init__(self, tag, directories, SPAMKEEP)

def drive(nsets):
    print options.display()

    hamdirs  = ["Data/Ham/Set%d" % i for i in range(1, nsets+1)]
    spamdirs = ["Data/Spam/Set%d" % i for i in range(1, nsets+1)]

    d = TestDriver.Driver()
    # Train it on all sets except the first.
    d.train(HamStream("%s-%d" % (hamdirs[1], nsets), hamdirs[1:]),
            SpamStream("%s-%d" % (spamdirs[1], nsets), spamdirs[1:]))

    # Now run nsets times, predicting pair i against all except pair i.
    for i in range(nsets):
        h = hamdirs[i]
        s = spamdirs[i]
        hamstream = HamStream(h, [h])
        spamstream = SpamStream(s, [s])

        if i > 0:
            # Forget this set.
            d.untrain(hamstream, spamstream)

        # Predict this set.
        d.test(hamstream, spamstream)
        d.finishtest()

        if i < nsets - 1:
            # Add this set back in.
            d.train(hamstream, spamstream)

    d.alldone()

def main():
    global SEED, HAMKEEP, SPAMKEEP
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:s:',
                                   ['ham-keep=', 'spam-keep='])
    except getopt.error, msg:
        usage(1, msg)

    nsets = seed = None
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)
        elif opt == '-s':
            seed = int(arg)
        elif opt == '--ham-keep':
            HAMKEEP = int(arg)
        elif opt == '--spam-keep':
            SPAMKEEP = int(arg)

    if args:
        usage(1, "Positional arguments not supported")
    if nsets is None:
        usage(1, "-n is required")
    if seed is not None:
        SEED = seed

    drive(nsets)

if __name__ == "__main__":
    main()
