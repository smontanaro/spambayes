#! /usr/bin/env python

# A driver for N-fold cross validation.

"""Usage: %(program)s [options] -n nsets

Where:
    -h
        Show usage and exit.
    -n int
        Number of Set directories (Data/Spam/Set1, ... and Data/Ham/Set1, ...).
        This is required.

If you only want to use some of the messages in each set,

    --ham-keep int
        The maximum number of msgs to use from each Ham set.  The msgs are
        chosen randomly.  See also the -s option.

    --spam-keep int
        The maximum number of msgs to use from each Spam set.  The msgs are
        chosen randomly.  See also the -s option.

    -s int
        A seed for the random number generator.  Has no effect unless
        at least on of {--ham-keep, --spam-keep} is specified.  If -s
        isn't specifed, the seed is taken from current time.

In addition, an attempt is made to merge bayescustomize.ini into the options.
If that exists, it can be used to change the settings in Options.options.
"""

from __future__ import generators

import sys

from Options import options
import TestDriver
import msgs

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def drive(nsets):
    print options.display()

    hamdirs  = ["Data/Ham/Set%d" % i for i in range(1, nsets+1)]
    spamdirs = ["Data/Spam/Set%d" % i for i in range(1, nsets+1)]

    d = TestDriver.Driver()
    # Train it on all sets except the first.
    d.train(msgs.HamStream("%s-%d" % (hamdirs[1], nsets), hamdirs[1:]),
            msgs.SpamStream("%s-%d" % (spamdirs[1], nsets), spamdirs[1:]))

    # Now run nsets times, predicting pair i against all except pair i.
    for i in range(nsets):
        h = hamdirs[i]
        s = spamdirs[i]
        hamstream = msgs.HamStream(h, [h])
        spamstream = msgs.SpamStream(s, [s])

        if i > 0:
            # Forget this set.
            d.untrain(hamstream, spamstream)

        # Predict this set.
        d.test(hamstream, spamstream)
        d.finishtest()

        if i < nsets - 1:
            # Add this set back in.
            d.train(hamstream, spamstream)

    d.alldone()

def main():
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:s:',
                                   ['ham-keep=', 'spam-keep='])
    except getopt.error, msg:
        usage(1, msg)

    nsets = seed = hamkeep = spamkeep = None
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)
        elif opt == '-s':
            seed = int(arg)
        elif opt == '--ham-keep':
            hamkeep = int(arg)
        elif opt == '--spam-keep':
            spamkeep = int(arg)

    if args:
        usage(1, "Positional arguments not supported")
    if nsets is None:
        usage(1, "-n is required")

    msgs.setparms(hamkeep, spamkeep, seed)
    drive(nsets)

if __name__ == "__main__":
    main()
