#! /usr/bin/env python

from timtoken import tokenize
from classifier import GrahamBayes
from Tester import Test
from timtest import Driver, Msg

import getopt
import mailbox
import random
from sets import Set
import sys

mbox_fmts = {"unix": mailbox.PortableUnixMailbox,
             "mmdf": mailbox.MmdfMailbox,
             "mh": mailbox.MHMailbox,
             "qmail": mailbox.Maildir,
             }

class MboxMsg(Msg):

    def __init__(self, fp, path, index):
        self.guts = fp.read()
        self.tag = "%s:%s %s" % (path, index, subject(self.guts))

class mbox(object):

    def __init__(self, path, indices=None):
        self.path = path
        self.indices = {}
        self.key = ''
        if indices is not None:
            self.key = " %s" % indices[0]
            for i in indices:
                self.indices[i] = 1

    def __repr__(self):
        return "<mbox: %s%s>" % (self.path, self.key)

    def __iter__(self):
        # Use a simple factory that just produces a string.
        mbox = mbox_fmts[FMT](open(self.path, "rb"),
                              lambda f: MboxMsg(f, self.path, i))

        i = 0
        while 1:
            msg = mbox.next()
            if msg is None:
                return
            i += 1
            if self.indices.get(i-1) or not self.indices:
                yield msg

def subject(buf):
    buf = buf.lower()
    i = buf.find('subject:')
    j = buf.find("\n", i)
    return buf[i:j]

def randindices(nelts, nresults):
    L = range(nelts)
    random.shuffle(L)
    chunk = nelts / nresults
    for i in range(nresults):
        yield Set(L[:chunk])
        del L[:chunk]

def sort(seq):
    L = list(seq)
    L.sort()
    return L

def main(args):
    global FMT
    
    FMT = "unix"
    NSETS = 5
    SEED = 101
    LIMIT = None
    opts, args = getopt.getopt(args, "f:n:s:l:")
    for k, v in opts:
        if k == '-f':
            FMT = v
        if k == '-n':
            NSETS = int(v)
        if k == '-s':
            SEED = int(v)
        if k == '-l':
            LIMIT = int(v)

    ham, spam = args

    random.seed(SEED)

    nham = len(list(mbox(ham)))
    nspam = len(list(mbox(spam)))

    if LIMIT:
        nham = min(nham, LIMIT)
        nspam = min(nspam, LIMIT)

    print "ham", ham, nham
    print "spam", spam, nspam

    testsets = []
    for iham in randindices(nham, NSETS):
        for ispam in randindices(nspam, NSETS):
            testsets.append((sort(iham), sort(ispam)))
            
    driver = Driver()

    for iham, ispam in testsets:
        driver.train(mbox(ham, iham), mbox(spam, ispam))
        for ihtest, istest in testsets:
            if (iham, ispam) == (ihtest, istest):
                continue
            driver.test(mbox(ham, ihtest), mbox(spam, istest))
        driver.finish()
    driver.alldone()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

