#! /usr/bin/env python

"""Split an mbox into N random directories of files.

Usage: %(program)s [-h] [-s seed] [-v] -n N sourcembox ... outdirbase

Options:
    -h / --help
        Print this help message and exit

    -s seed
        Seed the random number generator with seed (an integer).
        By default, use system time at startup to seed.

    -v
        Verbose.  Displays a period for each 100 messages parsed.
        May display other stuff.

    -n N
        The number of output mboxes desired.  This is required.

Arguments:
    sourcembox
        The mbox to split.

    outdirbase
        The base path + name prefix for each of the N output dirs.
        Output files have names of the form
            outdirbase + ("Set%%d/%%d" %% (i, n))

Example:
    %(program)s -s 123 -n5 Data/spam.mbox Data/Spam/Set

produces 5 directories, named Data/Spam/Set1 through Data/Spam/Set5.  Each
contains a random selection of the messages in spam.mbox, and together
they contain every message in spam.mbox exactly once.  Each has
approximately the same number of messages.  spam.mbox is not altered.  In
addition, the seed for the random number generator is forced to 123, so
that while the split is random, it's reproducible.
"""

import sys
import os
import random
import mailbox
import email
import getopt

import mboxutils

program = sys.argv[0]

def usage(code, msg=''):
    print >> sys.stderr, __doc__ % globals()
    if msg:
        print >> sys.stderr, msg
    sys.exit(code)

def _factory(fp):
    try:
        return email.message_from_file(fp)
    except email.Errors.MessageParseError:
        return ''

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:s:v', ['help'])
    except getopt.error, msg:
        usage(1, msg)

    n = None
    verbose = False
    for opt, arg in opts:
        if opt in ('-h', '--help'):
            usage(0)
        elif opt == '-s':
            random.seed(int(arg))
        elif opt == '-n':
            n = int(arg)
        elif opt == '-v':
            verbose = True

    if n is None or n <= 1:
        usage(1, "an -n value > 1 is required")

    if len(args) < 2:
        usage(1, "input mbox name and output base path are required")
    inputpaths, outputbasepath = args[:-1], args[-1]

    outdirs = [outputbasepath + ("%d" % i) for i in range(1, n+1)]
    for dir in outdirs:
        if not os.path.isdir(dir):
            os.makedirs(dir)

    counter = 0
    for inputpath in inputpaths:
        mbox = mboxutils.getmbox(inputpath)
        for msg in mbox:
            i = random.randrange(n)
            astext = str(msg)
            #assert astext.endswith('\n')
            counter += 1
            msgfile = open('%s/%d' % (outdirs[i], counter), 'wb')
            msgfile.write(astext)
            msgfile.close()
            if verbose:
                if counter % 100 == 0:
                    sys.stdout.write('.')
                    sys.stdout.flush()

    if verbose:
        print
        print counter, "messages split into", n, "directories"

if __name__ == '__main__':
    main()
