#! /usr/bin/env python

# Analyze a clim.pik file.

"""Usage: %(program)s  [options] [central_limit_pickle_file]

Options
    -h
        Show usage and exit.

Analyzes a pickle produced by clgen.py, and displays what would happen
if Rob Hooft's "RMS ZScore" scheme had been used to determine certainty
instead.

If no file is named on the cmdline, clim.pik is used.
"""


# surefactor: the ratio of the two p's to decide we're sure a message
# belongs to one of the two populations.  raising this number increases
# the "unsures" on both sides, decreasing the "sure fp" and "sure fn"
# rates.  A value of 1000 works well for me; at 10000 you get slightly
# less sure fp/fn at a cost of a lot more middle ground; at 10 you have
# much less work on the middle ground but ~50% more "sure false"
# scores.  This variable operates on messages that are "a bit of both
# ham and spam"
surefactor = 100     

# pminhamsure: The minimal pham at which we say it's surely ham
# lowering this value gives less "unsure ham" and more "sure ham"; it
# might however result in more "sure fn" 0.01 works well, but to accept
# a bit more fn, I set it to 0.005. This variable operates on messages
# that are "neither ham nor spam; but a bit more ham than spam"
pminhamsure = 0.005  

# pminspamsure: The minimal pspam at which we say it's surely spam
# lowering this value gives less "unsure spam" and more "sure spam"; it
# might however result in more "sure fp" Since most people find fp
# worse than fn, this value should most probably be higher than
# pminhamsure. 0.01 works well, but to accept a bit less fp, I set it
# to 0.02.  This variable operates on messages that are "neither ham
# nor spam; but a bit more spam than ham"
pminspamsure = 0.02  
                     
                     
# usetail: if False, use complete distributions to renormalize the
# Z-scores; if True, use only the worst tail value. I get worse results
# if I set this to True, so the default is False.
usetail = False      

# medianoffset: If True, set the median of the zham and zspam to 0
# before calculating rmsZ. If False, do not shift the data and hence
# assume that 0 is the center of the population. True seems to help for
# my data.
medianoffset = True  
                     
punsure = False      # Print unsure decisions (otherwise only sure-but-false)
exthist=0            # Prepare files to make histograms of values using an
                     # external program

import sys, math, os
import cPickle as pickle

program = sys.argv[0]
HAMVAL=2
SPAMVAL=3

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def chance(x):
    x=abs(x)
    if x<0.5:
        return 1
    p=-0.5*math.log(2*math.pi)-0.5*x**2-math.log(x)+math.log(1-(x**-2)+3*(x**-4))
    return min(1.0,math.exp(p))

def Z(p): # Reverse of chance
    x=math.log(p)
    z=math.sqrt(-2.0*x-math.log(2*math.pi))
    for n in range(8):
        errfac=chance(z)/p
        z=z+0.5*math.log(errfac)
    return z

knownfalse = {}
def readknownfalse():
    """Read a file named "knownfalse.dat" with the basename of the
       file as the first word on a line, and a short description
       following it."""
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

#   Pickle tuple contents:
#
#   0 tag         the msg identifier
#   1 is_spam     True if msg came from a spam Set, False if from a ham Set
#   2 zham        the msg zscore relative to the population ham
#   3 zspam       the msg zscore relative to the population spam
#   4 hmean       the raw mean ham score
#   5 smean       the raw mean spam score
#   6 n           the number of clues used to judge this msg

def drive(fname):
    print 'Reading', fname, '...'
    f = open(fname, 'rb')
    ham = pickle.load(f)
    spam = pickle.load(f)
    f.close()
    if exthist:
        fham=open('ham.dat','w')
        fspam=open('spam.dat','w')
    nham = 0
    hamham=[]
    for msg in ham:
        assert not msg[1]
        if exthist:
            print >> fham, "%.2f %.2f %.2f %.2f"%msg[2:6]
        hamham.append(msg[HAMVAL])
        nham += 1
    print "Nham=", nham
    hamham.sort()
    if medianoffset:
        hammedian=hamham[nham/2]
    else:
        hammedian=0.0
    if usetail:
        hamham.sort()
        fac = Z(10./nham)
        z1 = -(hamham[10]-hammedian)/fac
        z99 = (hamham[-10]-hammedian)/fac
        print "rmsZlo, rmsZhi= %.2f %.2f"%(z1,z99)
        rmszham = max(z1,z99)
    else:
        zhamsum2 = 0.0
        for msg in ham:
            zhamsum2 += (msg[HAMVAL]-hammedian)**2
        rmszham = math.sqrt(zhamsum2 / nham)
        print "RmsZham=", rmszham
        
    nspam = 0
    spamspam=[]
    for msg in spam:
        assert msg[1]
        if exthist:
            print >> fspam, "%.2f %.2f %.2f %.2f"%msg[2:6]
        spamspam.append(msg[SPAMVAL])
        nspam += 1
    print "Nspam=", nspam
    spamspam.sort()
    if medianoffset:
        spammedian=spamspam[nspam/2]
    else:
        spammedian=0.0
    if usetail:
        fac=Z(10./nspam)
        z1=-(spamspam[10]-spammedian)/fac
        z99=(spamspam[-10]-spammedian)/fac
        print "rmsZlo, rmsZhi= %.2f %.2f"%(z1,z99)
        rmszspam = max(z1,z99)
    else:
        zspamsum2 = 0.0
        for msg in spam:
            zspamsum2 += (msg[SPAMVAL]-spammedian)**2
        rmszspam = math.sqrt(zspamsum2 / nspam)
        print "RmsZspam=", rmszspam
    
    if exthist:
        fham.close()
        fspam.close()
    #========= Analyze ham
    print "=" * 70
    print "HAM:"
    nsureok = nunsureok = nunsurenok = nsurenok = 0
    for msg in ham:
        zham = (msg[HAMVAL]-hammedian) / rmszham
        zspam = (msg[SPAMVAL]-spammedian) / rmszspam
        cham = chance(zham)
        cspam = chance(zspam)
        if cham > surefactor*cspam and cham > pminhamsure:
            nsureok += 1 # very certain
        elif cham > cspam:
            nunsureok += 1
            #print "Unsure",msg[0]
            #prknown(msg[0])
        else:
            if cspam > surefactor*cham and cspam > pminspamsure:
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
        zham = (msg[HAMVAL]-hammedian) / rmszham
        zspam = (msg[SPAMVAL]-spammedian) / rmszspam
        cham = chance(zham)
        cspam = chance(zspam)
        if cspam > surefactor*cham and cspam > pminspamsure:
            nsureok += 1 # very certain
        elif cspam > cham:
            nunsureok += 1
            #print "Unsure",msg[0]
            #prknown(msg[0])
        else:
            if cham > surefactor*cspam and cham > pminhamsure:
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
