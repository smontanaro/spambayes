#!/usr/bin/env python

## A hammie front-end to make the simple stuff simple.
##
##
## The intent is to call this from procmail and its ilk like so:
##
##   :0 fw
##   | hammiefilter.py
## 
## Then, you can set up your MUA to pipe ham and spam to it, one at a
## time, by calling it with either the -g or -s options, respectively.
##
## Author: Neale Pickett <neale@woozle.org>
##

"""Usage: %(program)s [option]

Where [option] is one of:
    -h
        show usage and exit
    -n
        create a new database
    -g
        train on stdin as a good (ham) message
    -s
        train on stdin as a bad (spam) message

If neither -g nor -s is given, stdin will be scored: the same message,
with a new header containing the score, will be send to stdout.
"""

import sys
import getopt
import hammie
from Options import options

# See Options.py for explanations of these properties
DBNAME = options.persistent_storage_file
USEDB = options.persistent_use_database
program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def hammie_open(mode):
    b = hammie.createbayes(DBNAME, USEDB, mode)
    return hammie.Hammie(b)

def newdb():
    hammie_open('n')
    print "Created new database in", DBNAME

def filter():
    h = hammie_open('r')
    msg = sys.stdin.read()
    print h.filter(msg)

def train_ham():
    h = hammie_open('w')
    msg = sys.stdin.read()
    h.train_ham(msg)
    h.update_probabilities()

def train_spam():
    h = hammie_open('w')
    msg = sys.stdin.read()
    h.train_spam(msg)
    h.update_probabilities()


def main():
    action = filter
    opts, args = getopt.getopt(sys.argv[1:], 'hngs')
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-g':
            action = train_ham
        elif opt == '-s':
            action = train_spam
        elif opt == "-n":
            action = newdb
    action()

if __name__ == "__main__":
    main()

