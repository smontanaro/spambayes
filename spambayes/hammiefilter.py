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

import os
import sys
import getopt
import hammie
import Options
import StringIO

# See Options.py for explanations of these properties
program = sys.argv[0]

# Options
options = Options.options

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

class HammieFilter(object):
    def __init__(self):
        options = Options.options
        options.mergefiles(['/etc/hammierc',
                            os.path.expanduser('~/.hammierc')])
        
        self.dbname = options.hammiefilter_persistent_storage_file
        self.dbname = os.path.expanduser(self.dbname)
        self.usedb = options.hammiefilter_persistent_use_database
        

    def newdb(self):
        h = hammie.open(self.dbname, self.usedb, 'n')
        h.store()
        print "Created new database in", self.dbname

    def filter(self):
        h = hammie.open(self.dbname, self.usedb, 'r')
        msg = sys.stdin.read()
        print h.filter(msg)

    def train_ham(self):
        h = hammie.open(self.dbname, self.usedb, 'c')
        msg = sys.stdin.read()
        h.train_ham(msg)
        h.store()

    def train_spam(self):
        h = hammie.open(self.dbname, self.usedb, 'c')
        msg = sys.stdin.read()
        h.train_spam(msg)
        h.store()

def main():
    h = HammieFilter()
    action = h.filter
    opts, args = getopt.getopt(sys.argv[1:], 'hngs')
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-g':
            action = h.train_ham
        elif opt == '-s':
            action = h.train_spam
        elif opt == "-n":
            action = h.newdb

    action()

if __name__ == "__main__":
    main()

