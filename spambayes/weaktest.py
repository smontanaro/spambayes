#! /usr/bin/env python

# A test driver using "the standard" test directory structure.
# This simulates a user that gets E-mail, and only trains on fp,
# fn and unsure messages. It starts by training on the first 30
# messages, and from that point on well classified messages will
# not be used for training. This can be used to see what the performance
# of the scoring algorithm is under such conditions. Questions are:
#  * How does the size of the database behave over time?
#  * Does the classification get better over time?
#  * Are there other combinations of parameters for the classifier
#    that make this better behaved than the default values?


"""Usage: %(program)s  [options] -n nsets

Where:
    -h
        Show usage and exit.
    -n int
        Number of Set directories (Data/Spam/Set1, ... and Data/Ham/Set1, ...).
        This is required.

In addition, an attempt is made to merge bayescustomize.ini into the options.
If that exists, it can be used to change the settings in Options.options.
"""

from __future__ import generators

import sys,os

from Options import options
import hammie

import msgs
import CostCounter

program = sys.argv[0]

debug = 0

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def drive(nsets):
    print options.display()

    spamdirs = [options.spam_directories % i for i in range(1, nsets+1)]
    hamdirs  = [options.ham_directories % i for i in range(1, nsets+1)]

    spamfns = [(x,y,1) for x in spamdirs for y in os.listdir(x)]
    hamfns = [(x,y,0) for x in hamdirs for y in os.listdir(x)]

    nham = len(hamfns)
    nspam = len(spamfns)
    cc = CostCounter.default()

    allfns = {}
    for fn in spamfns+hamfns:
        allfns[fn] = None

    d = hammie.Hammie(hammie.createbayes('weaktest.db', False))

    n = 0
    unsure = 0
    hamtrain = 0
    spamtrain = 0
    fp = 0
    fn = 0
    SPC = options.spam_cutoff
    HC = options.ham_cutoff
    for dir,name, is_spam in allfns.iterkeys():
        n += 1
        m=msgs.Msg(dir, name).guts
        if debug:
            print "trained:%dH+%dS fp:%d fn:%d unsure:%d before %s/%s"%(hamtrain,spamtrain,fp,fn,unsure,dir,name),
        if hamtrain + spamtrain > 30:
            scr=d.score(m)
        else:
            scr=0.50
        if debug:
            print "score:%.3f"%scr,
        if is_spam:
            cc.spam(scr)
        else:
            cc.ham(scr)
        if scr < SPC and is_spam:
            if scr < HC:
                fn += 1
                if debug:
                    print "fn"
            else:
                unsure += 1
                if debug:
                    print "Unsure"
            spamtrain += 1
            d.train_spam(m)
            d.update_probabilities()
        elif scr > HC and not is_spam:
            if scr > SPC:
                fp += 1
                if debug:
                    print "fp"
                else:
                    print "fp: %s score:%.4f"%(os.path.join(dir, name), scr)
            else:
                unsure += 1
                if debug:
                    print "Unsure"
            hamtrain += 1
            d.train_ham(m)
            d.update_probabilities()
        else:
            if debug:
                print "OK"
        if n % 100 == 0:
            print "%5d trained:%dH+%dS wrds:%d fp:%d fn:%d unsure:%d"%(
                n, hamtrain, spamtrain, len(d.bayes.wordinfo), fp, fn, unsure)
    print "Total messages %d (%d ham and %d spam)"%(len(allfns), nham, nspam)
    print "Total unsure (including 30 startup messages): %d (%.1f%%)"%(
        unsure, unsure * 100.0 / len(allfns))
    print "Trained on %d ham and %d spam"%(hamtrain, spamtrain)
    print "fp: %d fn: %d"%(fp, fn)
    print cc

def main():
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hn:')
    except getopt.error, msg:
        usage(1, msg)

    nsets = None
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)

    if args:
        usage(1, "Positional arguments not supported")
    if nsets is None:
        usage(1, "-n is required")

    drive(nsets)

if __name__ == "__main__":
    main()
