#! /usr/bin/env python
"""mboxtest.py: A test driver for classifier.

Usage: mboxtest.py [options] <ham> <spam>

Options:
    -f FMT
        One of unix, mmdf, mh, or qmail.  Specifies mailbox format for
        ham and spam files.  Default is unix.

    -n NSETS
        Number of test sets to create for a single mailbox.  Default is 5.

    -s SEED
        Seed for random number generator.  Default is 101.

    -m MSGS
        Read no more than MSGS messages from mailbox.
"""

import getopt
import mailbox
import random
from sets import Set
import sys

from tokenizer import Tokenizer, subject_word_re, tokenize_word, tokenize
from TestDriver import Driver
from timtest import Msg

mbox_fmts = {"unix": mailbox.PortableUnixMailbox,
             "mmdf": mailbox.MmdfMailbox,
             "mh": mailbox.MHMailbox,
             "qmail": mailbox.Maildir,
             }

class MyTokenizer(Tokenizer):

    skip = {'received': 1,
            'date': 1,
            'x-from_': 1,
            }

    def tokenize_headers(self, msg):
        for k, v in msg.items():
            k = k.lower()
            if k in self.skip or k.startswith('x-vm'):
                continue
            for w in subject_word_re.findall(v):
                for t in tokenize_word(w):
                    yield "%s:%s" % (k, t)

class MboxMsg(Msg):

    def __init__(self, fp, path, index):
        self.guts = fp.read()
        self.tag = "%s:%s %s" % (path, index, subject(self.guts))

    def __str__(self):
        lines = []
        i = 0
        for line in self.guts.split("\n"):
            skip = False
            for skip_prefix in 'X-', 'Received:', '\t',:
                if line.startswith(skip_prefix):
                    skip = True
            if skip:
                continue
            i += 1
            if i > 100:
                lines.append("... truncated")
                break
            lines.append(line)
        return "\n".join(lines)

##    tokenize = MyTokenizer().tokenize

    def __iter__(self):
        return tokenize(self.guts)

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
    MAXMSGS = None
    opts, args = getopt.getopt(args, "f:n:s:m:")
    for k, v in opts:
        if k == '-f':
            FMT = v
        if k == '-n':
            NSETS = int(v)
        if k == '-s':
            SEED = int(v)
        if k == '-m':
            MAXMSGS = int(v)

    ham, spam = args

    random.seed(SEED)

    nham = len(list(mbox(ham)))
    nspam = len(list(mbox(spam)))

    if MAXMSGS:
        nham = min(nham, MAXMSGS)
        nspam = min(nspam, MAXMSGS)

    print "ham", ham, nham
    print "spam", spam, nspam

    testsets = []
    for iham in randindices(nham, NSETS):
        for ispam in randindices(nspam, NSETS):
            testsets.append((sort(iham), sort(ispam)))

    driver = Driver()

    for iham, ispam in testsets:
        driver.new_classifier()
        driver.train(mbox(ham, iham), mbox(spam, ispam))
        for ihtest, istest in testsets:
            if (iham, ispam) == (ihtest, istest):
                continue
            driver.test(mbox(ham, ihtest), mbox(spam, istest))
        driver.finishtest()
    driver.alldone()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
