#! /usr/bin/env python
"""Score a message provided on stdin and show the evidence."""

import ZODB
from ZEO.ClientStorage import ClientStorage

from tokenizer import tokenize

import email
import sys

import pspam.options

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


def main(fp):
    cs = ClientStorage("/var/tmp/zeospam")
    db = ZODB.DB(cs)
    r = db.open().root()

    # make sure scoring uses the right set of options
    pspam.options.mergefile("/home/jeremy/src/vmspam/vmspam.ini")

    p = r["profile"]

    msg = email.message_from_file(fp)
    prob, evidence = p.classifier.spamprob(tokenize(msg), True)
    print "Score:", prob
    print
    print "Clues"
    print "-----"
    for clue, prob in evidence:
        print clue, prob
##    print
##    print msg
        
if __name__ == "__main__":
    main(sys.stdin)
