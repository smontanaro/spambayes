#!/usr/bin/env python

"""
Demonstration of n-way classification possibilities.

Usage: %(prog)s [ -h ] tag=db ...

-h - print this message and exit.

All args are of the form 'tag=db' where 'tag' is the tag to be given in the
X-Spambayes-Classification: header.  A single message is read from stdin and
a modified message sent to stdout.  The message is compared against each
database in turn.  If its score exceeds the spam threshold when scored
against a particular database, an X-Spambayes-Classification header is added
and the modified message is written to stdout.  If none of the comparisons
yields a definite classification, the message is written with an
'X-Spambayes-Classification: unsure' header.

Training is left up to the user.  In general, you want to train so that a
message in a particular category will score as spam when checked against
that category's training database.  For example, suppose you have the
following mbox formatted files: python, music, family, cars.  If you wanted
to create a training database for each of them you could execute this
series of mboxtrain.py commands:

    mboxtrain.py -d python.db -s python -g music -g family -g cars
    mboxtrain.py -d music.db  -g python -s music -g family -g cars
    mboxtrain.py -d family.db -g python -g music -s family -g cars
    mboxtrain.py -d cars.db   -g python -g music -g family -s cars

You'd then compare messages using a %(prog)s command like this:

    %(prog)s python=python.db music=music.db family=family.db cars=cars.db
"""

import getopt
import sys
import os
from spambayes import hammie, mboxutils, Options

prog = os.path.basename(sys.argv[0])

def help():
    print >> sys.stderr, __doc__ % globals()

def main(args):
    opts, args = getopt.getopt(args, "h")

    for opt, arg in opts:
        if opt == '-h':
            help()
            return 0

    tagdb_list = []
    msg = mboxutils.get_message(sys.stdin)
    try:
        del msg["X-Spambayes-Classification"]
    except KeyError:
        pass
    for pair in args:
        tag, db = pair.split('=', 1)
        h = hammie.open(db, True, 'r')
        score = h.score(msg)
        if score >= Options.options.spam_cutoff:
            msg["X-Spambayes-Classification"] = "%s; %.2f" % (tag, score)
            break
    else:
        msg["X-Spambayes-Classification"] = "unsure"

    sys.stdout.write(msg.as_string(unixfrom=(msg.get_unixfrom()
                                             is not None)))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
