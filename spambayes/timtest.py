#! /usr/bin/env python
# At the moment, this requires Python 2.3 from CVS (heapq, Set, enumerate).

# A test driver using "the standard" test directory structure.  See also
# rates.py and cmp.py for summarizing results.

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
        guts = f.read()
        f.close()
        self.guts = guts

    def __iter__(self):
        return tokenize(self.guts)

    def __hash__(self):
        return hash(self.tag)

    def __eq__(self, other):
        return self.tag == other.tag

    def __str__(self):
        return self.guts

class MsgStream(object):
    def __init__(self, directory):
        self.directory = directory

    def __str__(self):
        return self.directory

    def produce(self):
        directory = self.directory
        for fname in os.listdir(directory):
            yield Msg(directory, fname)

    def produce(self):
        import random
        directory = self.directory
        all = os.listdir(directory)
        random.seed(hash(directory))
        random.shuffle(all)
        for fname in all[-1500:-1000:]:
            yield Msg(directory, fname)

    def __iter__(self):
        return self.produce()

def drive(nsets):
    print options.display()

    spamdirs = ["Data/Spam/Set%d" % i for i in range(1, nsets+1)]
    hamdirs  = ["Data/Ham/Set%d" % i for i in range(1, nsets+1)]
    spamhamdirs = zip(spamdirs, hamdirs)

    d = Driver()
    for spamdir, hamdir in spamhamdirs:
        d.train(MsgStream(hamdir), MsgStream(spamdir))
        for sd2, hd2 in spamhamdirs:
            if (sd2, hd2) == (spamdir, hamdir):
                continue
            d.test(MsgStream(hd2), MsgStream(sd2))
        d.finishtest()
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
