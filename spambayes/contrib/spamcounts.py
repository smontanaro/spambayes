#!/usr/bin/env python

"""
Check spamcounts for various tokens or patterns

usage %(prog)s [ -h ] [ -r ] [ -d db ] [ -p ] [ -t ] ...

-h    - print this documentation and exit.
-r    - treat tokens as regular expressions - may not be used with -t
-d db - use db instead of the default found in the options file
-p    - db is actually a pickle
-t    - read message from stdin, tokenize it, then display their counts
        may not be used with -r
"""

from __future__ import division

import sys
import getopt
import re
import sets
import os
import shelve
import pickle
import csv

from spambayes.Options import options
from spambayes.tokenizer import tokenize

prog = sys.argv[0]

def usage(msg=None):
    if msg is not None:
        print >> sys.stderr, msg
    print >> sys.stderr, __doc__.strip() % globals()

# From msgs on spambayes mailing list, spam prob is calculated thusly:
## hc = ham token count
## nh = total number of ham messages
## sc = spam token count
## ns = total number of spam messages
## hr = ham ratio = hc / nh
## sr = spam ratio = sc / ns
## p = base spam probability = sr / (sr + hr)
## S = unknown word strength (static factor = 0.45 by default)
## x = unknown word probability (static factor = 0.5 by default)
## n = total number of messages the token appeared in = hc + sc
## sp = final spam probability = ((S * x) + (n * p)) / (S + n)


def print_spamcounts(tokens, db, use_re):
    if use_re:
        s = sets.Set()
        keys = db.keys()
        for pat in tokens:
            for k in keys:
                if re.search(pat, k) is not None:
                    s.add(k)
        tokens = list(s)

    S = options["Classifier", "unknown_word_strength"]
    x = options["Classifier", "unknown_word_prob"]
    _, ns, nh = db["saved state"]

    writer = csv.writer(sys.stdout)
    writer.writerow(("token", "nspam", "nham", "spam prob"))
    seen = sets.Set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)

        sc, hc = db.get(t, (0, 0))
        if sc == hc == 0:
            continue

        hr = hc / nh
        sr = sc / ns
        p = sr / (sr + hr)
        n = hc + sc
        sp = ((S * x) + (n * p)) / (S + n)

        writer.writerow((t, sc, hc, sp))

def main(args):
    try:
        opts, args = getopt.getopt(args, "hrd:t",
                                   ["help", "re", "database=", "pickle",
                                    "tokenize"])
    except getopt.GetoptError, msg:
        usage(msg)
        return 1

    usere = False
    dbname = options["Storage", "persistent_storage_file"]
    ispickle = False
    tokenizestdin = False
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            return 0
        elif opt in ("-d", "--database"):
            dbname = arg
        elif opt in ("-r", "--re"):
            usere = True
        elif opt in ("-p", "--pickle"):
            ispickle = True
        elif opt in ("-t", "--tokenize"):
            tokenizestdin = True

    if usere and tokenizestdin:
        usage("-r and -t may not be used at the same time")
        return 1

    dbname = os.path.expanduser(dbname)
    print >> sys.stderr, "db:", dbname
    if ispickle:
        db = pickle.load(file(dbname))
    else:
        db = shelve.open(dbname, flag='r')

    if tokenizestdin:
        args = tokenize(sys.stdin)

    if args:
        print_spamcounts(args, db, usere)
        return 0
    else:
        usage("need tokens on cmd line or -t w/ msg on stdin")
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
