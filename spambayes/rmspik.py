#! /usr/bin/env python

# Analyze a clim.pik file.

"""Usage: %(program)s  [options] [central_limit_pickle_file]

An example analysis program showing to access info from a central-limit
pickle file created by clgen.py.  This program produces histograms of
various things.

Scores for all predictions are saved at the end of binary pickle clim.pik.
This contains two lists of tuples, the first list with a tuple for every
ham predicted, the second list with a tuple for every spam predicted.  Each
tuple has these values:

    tag         the msg identifier
    is_spam     True if msg came from a spam Set, False if from a ham Set
    zham        the msg zscore relative to the population ham
    zspam       the msg zscore relative to the population spam
    hmean       the raw mean ham score
    smean       the raw mean spam score
    n           the number of clues used to judge this msg

Note that hmean and smean are the same under use_central_limit; they're
very likely to differ under use_central_limit2.

Where:
    -h
        Show usage and exit.

If no file is named on the cmdline, clim.pik is used.
"""

surefactor = 1000 # This is basically the inverse of the accepted fp/fn rate
punsure = False # Print unsure decisions (otherwise only sure-but-false)

import sys,math,os
import cPickle as pickle

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def chance(x):
    if x>=0:
        return 1.0
    x=-x/math.sqrt(2)
    if x<1.4:
        return 1.0
    assert x>=1.4
    x=float(x)
    pre=math.exp(-x**2)/math.sqrt(math.pi)/x
    post=1-(1/(2*x**2))
    return pre*post

knownfalse = {}

def readknownfalse():
    global knownfalse
    knownfalse = {}
    try:
        f = open('knownfalse.dat')
    except IOError:
        return
    for line in f:
        key, desc = line.split(None, 1)
        knownfalse[key] = desc[:-1]
    f.close()
    print "%d descriptions from knownfalse.dat" % len(knownfalse)

def prknown(tag):
    bn = os.path.basename(tag)
    if bn in knownfalse:
        print " ==>", knownfalse[bn]

def drive(fname):
    print 'Reading', fname, '...'
    f = open(fname, 'rb')
    ham = pickle.load(f)
    spam = pickle.load(f)
    f.close()

    zhamsum2 = 0.0
    nham = 0
    for msg in ham:
        if msg[1]:
            print "spam in ham",msg
        else:
            zhamsum2 += msg[2]**2
            nham += 1
    rmszham = math.sqrt(zhamsum2 / nham)
    print "Nham=", nham
    print "RmsZham=", rmszham

    zspamsum2 = 0.0
    nspam = 0
    for msg in spam:
        if not msg[1]:
            print "ham in spam",msg
        else:
            zspamsum2 += msg[3]**2
            nspam += 1
    rmszspam = math.sqrt(zspamsum2 / nspam)
    print "Nspam=", nspam
    print "RmsZspam=", rmszspam

    #========= Analyze ham
    print "=" * 70
    print "HAM:"
    nsureok = nunsureok = nunsurenok = nsurenok = 0
    for msg in ham:
        zham = msg[2] / rmszham
        zspam = msg[3] / rmszspam
        cham = chance(zham)
        cspam = chance(zspam)
        if cham > surefactor*cspam and cham > 0.01:
            nsureok += 1 # very certain
        elif cham > cspam:
            nunsureok += 1
            #print "Unsure",msg[0]
            #prknown(msg[0])
        else:
            if cspam > surefactor*cham and cspam > 0.01:
                reason = "SURE!"
                nsurenok += 1
            elif cham < 0.01 and cspam < 0.01:
                reason = "neither?"
                nunsurenok += 1
            elif cham > 0.1 and cspam > 0.1:
                reason = "both?"
                nunsurenok += 1
            else:
                reason = "Unsure"
                nunsurenok += 1
            if reason=="SURE!" or punsure:
                print "FALSE POSITIVE: zham=%.2f zspam=%.2f %s %s" % (
                      zham, zspam, msg[0], reason)
                prknown(msg[0])
    print "Sure/ok      ", nsureok
    print "Unsure/ok    ", nunsureok
    print "Unsure/not ok", nunsurenok
    print "Sure/not ok  ", nsurenok
    print "Unsure rate = %.2f%%" % (100.*(nunsureok + nunsurenok) / len(ham))
    print "Sure fp rate = %.2f%%; Unsure fp rate = %.2f%%" % (
          100.*nsurenok / (nsurenok + nsureok),
          100.*nunsurenok / (nunsurenok + nunsureok))
    #========= Analyze spam
    print "="*70
    print "SPAM:"
    nsureok = nunsureok = nunsurenok = nsurenok = 0
    for msg in spam:
        zham = msg[2] / rmszham
        zspam = msg[3] / rmszspam
        cham = chance(zham)
        cspam = chance(zspam)
        if cspam > surefactor*cham and cspam > 0.01:
            nsureok += 1 # very certain
        elif cspam > cham:
            nunsureok += 1
            #print "Unsure",msg[0]
            #prknown(msg[0])
        else:
            if cham > surefactor*cspam and cham > 0.01:
                reason = "SURE!"
                nsurenok += 1
            elif cham < 0.01 and cspam < 0.01:
                reason = "neither?"
                nunsurenok += 1
            elif cham > 0.1 and cspam > 0.1:
                reason = "both?"
                nunsurenok += 1
            else:
                reason = "Unsure"
                nunsurenok += 1
            if reason=="SURE!" or punsure:
                print "FALSE NEGATIVE: zham=%.2f zspam=%.2f %s %s" % (
                      zham, zspam, msg[0], reason)
                prknown(msg[0])
    print "Sure/ok      ", nsureok
    print "Unsure/ok    ", nunsureok
    print "Unsure/not ok", nunsurenok
    print "Sure/not ok  ", nsurenok
    print "Unsure rate = %.2f%%"% (100.*(nunsureok + nunsurenok) / len(ham))
    print "Sure fn rate = %.2f%%; Unsure fn rate = %.2f%%" % (
          100.*nsurenok / (nsurenok + nsureok),
          100.*nunsurenok / (nunsurenok + nunsureok))

def main():
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'h')
    except getopt.error, msg:
        usage(1, msg)

    nbuckets = 100
    for opt, arg in opts:
        if opt == '-h':
            usage(0)

    fname = 'clim.pik'
    if args:
        fname = args.pop(0)
    if args:
        usage(1, "No more than one positional argument allowed")

    readknownfalse()
    drive(fname)

if __name__ == "__main__":
    main()
