#!/usr/bin/env python

"""
Train to exhaustion: train repeatedly on a pile of ham and spam until
everything scores properly.

usage %(prog)s [ -h ] -g file -s file [ -d file | -p file ] [ -m N ] [ -r N ]

-h      - print this documentation and exit.

-g file - take ham from file

-s file - take spam from file

-d file - use a database-based classifier named file

-p file - use a pickle-based classifier named file

-m N    - train on at most N messages (nham == N/2 and nspam == N/2)

-r N    - run at most N rounds (default %(MAXROUNDS)s), even if not
          all messages score correctly

See Gary Robinson's blog:

    http://www.garyrobinson.net/2004/02/spam_filtering_.html
"""

from __future__ import division

import sys
import getopt
import os
import datetime

from spambayes import storage
from spambayes import Options
from spambayes import mboxutils
from spambayes.tokenizer import tokenize

prog = os.path.basename(sys.argv[0])

MAXROUNDS = 10

def usage(msg=None):
    if msg is not None:
        print >> sys.stderr, msg
    print >> sys.stderr, __doc__.strip() % globals()

def train(store, ham, spam, maxmsgs, maxrounds):
    smisses = hmisses = round = 0
    ham_cutoff = Options.options["Categorization", "ham_cutoff"]
    spam_cutoff = Options.options["Categorization", "spam_cutoff"]

    while round < maxrounds and (hmisses or smisses or round == 0):
        hambone = mboxutils.getmbox(ham)
        spamcan = mboxutils.getmbox(spam)
        round += 1
        hmisses = smisses = nmsgs = 0
        start = datetime.datetime.now()
        try:
            while not maxmsgs or nmsgs < maxmsgs:
                hammsg = hambone.next()
                spammsg = spamcan.next()

                nmsgs += 2
                sys.stdout.write("\r%5d" % nmsgs)
                sys.stdout.flush()

                if store.spamprob(tokenize(hammsg)) > ham_cutoff:
                    hmisses += 1
                    store.learn(tokenize(hammsg), False)

                if store.spamprob(tokenize(spammsg)) < spam_cutoff:
                    smisses += 1
                    store.learn(tokenize(spammsg), True)

        except StopIteration:
            pass
            
        delta = datetime.datetime.now()-start
        seconds = delta.seconds + delta.microseconds/1000000

        print "\rround: %2d, msgs: %4d, ham misses: %3d, spam misses: %3d, %.1fs" % \
              (round, nmsgs, hmisses, smisses, seconds)

    nhamleft = 0
    try:
        while True:
            hambone.next()
            nhamleft += 1
    except StopIteration:
        if nhamleft: print nhamleft, "untrained hams"

    nspamleft = 0
    try:
        while True:
            spamcan.next()
            nspamleft += 1
    except StopIteration:
        if nspamleft: print nspamleft, "untrained spams"

def main(args):
    try:
        opts, args = getopt.getopt(args, "hg:s:d:p:o:m:r:",
                                   ["help", "good=", "spam=",
                                    "database=", "pickle=",
                                    "option=", "max=", "maxrounds="])
    except getopt.GetoptError, msg:
        usage(msg)
        return 1

    ham = spam = dbname = usedb = None
    maxmsgs = 0
    maxrounds = MAXROUNDS
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            return 0
        elif opt in ("-g", "--good"):
            ham = arg
        elif opt in ("-s", "--spam"):
            spam = arg
        elif opt in ("-m", "--max"):
            maxmsgs = int(arg)
        elif opt in ("-r", "--maxrounds"):
            maxrounds = int(arg)
        elif opt in ('-o', '--option'):
            Options.options.set_from_cmdline(arg, sys.stderr)
            
    if ham is None or spam is None:
        usage("require both ham and spam piles")
        return 1

    dbname, usedb = storage.database_type(opts)

    try:
        os.unlink(dbname)
    except OSError:
        pass

    store = storage.open_storage(dbname, usedb)

    train(store, ham, spam, maxmsgs, maxrounds)

    store.store()

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
