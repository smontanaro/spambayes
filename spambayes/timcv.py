#! /usr/bin/env python
# At the moment, this requires Python 2.3 from CVS (heapq, Set, enumerate).

# A driver for N-fold cross validation.

"""Usage: %(program)s [-h] -n nsets

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

from Options import options
from tokenizer import tokenize
from TestDriver import Driver

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class Msg(object):
    def __init__(self, dir, name):
        path = dir + "/" + name
        self.tag = path
        f = open(path, 'rb')
        self.guts = f.read()
        f.close()

    def __iter__(self):
        return tokenize(self.guts)

    def __hash__(self):
        return hash(self.tag)

    def __eq__(self, other):
        return self.tag == other.tag

    def __str__(self):
        return self.guts

class MsgStream(object):
    def __init__(self, tag, directories):
        self.tag = tag
        self.directories = directories

    def __str__(self):
        return self.tag

    def produce(self):
        for directory in self.directories:
            for fname in os.listdir(directory):
                yield Msg(directory, fname)

    def xproduce(self):
        import random
        keep = 'Spam' in self.directories[0] and 300 or 300
        for directory in self.directories:
            all = os.listdir(directory)
            random.seed(hash(max(all)) ^ 0x12345678) # reproducible across calls
            random.shuffle(all)
            for fname in all[:keep]:
                yield Msg(directory, fname)

    def __iter__(self):
        return self.produce()

def drive(nsets):
    print options.display()

    hamdirs  = ["Data/Ham/Set%d" % i for i in range(1, nsets+1)]
    spamdirs = ["Data/Spam/Set%d" % i for i in range(1, nsets+1)]

    d = Driver()
    # Train it on all sets except the first.
    d.train(MsgStream("%s-%d" % (hamdirs[1], nsets), hamdirs[1:]),
            MsgStream("%s-%d" % (spamdirs[1], nsets), spamdirs[1:]))

    # Now run nsets times, predicting pair i against all except pair i.
    for i in range(nsets):
        h = hamdirs[i]
        s = spamdirs[i]
        hamstream = MsgStream(h, [h])
        spamstream = MsgStream(s, [s])

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
    if nsets is None:
        usage(1, "-n is required")

    drive(nsets)
