#!/usr/bin/env python

"""
table.py base1 base2 ... baseN

Combines output from base1.txt, base2.txt, etc., which are created by
the TestDriver (such as timcv.py) output, and displays tabulated
comparison statistics to stdout.  Each input file is represented by
one column in the table.
"""

import sys
import re

# Return
#  (
#   ham tested,
#   spam tested,
#   total f-p,
#   total f-n,
#   total unsure,
#   average f-p rate,
#   average f-n rate,
#   average unsure rate,
#   real cost,
#   best cost,
#   ham score deviation for all runs,
#   spam score deviations for all runs,
# )
# from summary file f.
def suck(f):
    hamdevall = spamdevall = (0.0, 0.0)
    cost = 0.0
    bestcost = 0.0
    fp = 0
    fn = 0
    un = 0
    fpp = 0.0
    fnp = 0.0
    unp = 0.0
    htest = 0
    stest = 0

    get = f.readline
    while 1:
        line = get()
        if line.startswith('-> <stat> tested'):
            # -> <stat> tested 1910 hams & 948 spams against 2741 hams & 948 spams
            #  0      1      2    3    4 5   6
            print line,

        elif line.find(' items; mean ') > 0 and line.find('for all runs') > 0:
            # -> <stat> Ham scores for all runs: 2741 items; mean 0.86; sdev 6.28
            #                                             0          1          2
            vals = line.split(';')
            mean = float(vals[1].split()[-1])
            sdev = float(vals[2].split()[-1])
            val = (mean, sdev)
            ntested = int(vals[0].split()[-2])
            typ = vals[0].split()[2]
            if line.find('for all runs') != -1:
                if typ == 'Ham':
                    hamdevall = val
                    htest = ntested
                else:
                    spamdevall = val
                    stest = ntested

        elif line.startswith('-> best cost for all runs: $'):
            # -> best cost for all runs: $28.20
            bestcost = float(line.split('$')[-1])

        elif line.startswith('-> <stat> all runs false positives: '):
            fp = int(line.split()[-1])

        elif line.startswith('-> <stat> all runs false negatives: '):
            fn = int(line.split()[-1])

        elif line.startswith('-> <stat> all runs unsure: '):
            un = int(line.split()[-1])

        elif line.startswith('-> <stat> all runs false positive %: '):
            fpp = float(line.split()[-1])

        elif line.startswith('-> <stat> all runs false negative %: '):
            fnp = float(line.split()[-1])

        elif line.startswith('-> <stat> all runs unsure %: '):
            unp = float(line.split()[-1])

        elif line.startswith('-> <stat> all runs cost: '):
            cost = float(line.split('$')[-1])
            break

    return (htest, stest, fp, fn, un, fpp, fnp, unp, cost, bestcost,
            hamdevall, spamdevall)

def windowsfy(fn):
    import os
    if os.path.exists(fn + '.txt'):
        return fn + '.txt'
    else:
        return fn

fname = "filename: "
fnam2 = "          "
ratio = "ham:spam: "
rat2  = "          "
fptot = "fp total: "
fpper = "fp %:     "
fntot = "fn total: "
fnper = "fn %:     "
untot = "unsure t: "
unper = "unsure %: "
rcost = "real cost:"
bcost = "best cost:"

hmean = "h mean:   "
hsdev = "h sdev:   "
smean = "s mean:   "
ssdev = "s sdev:   "
meand = "mean diff:"
kval  = "k:        "

for filename in sys.argv[1:]:
    filename = windowsfy(filename)
    (htest, stest, fp, fn, un, fpp, fnp, unp, cost, bestcost,
     hamdevall, spamdevall) = suck(file(filename))
    if filename.endswith('.txt'):
        filename = filename[:-4]
    filename = filename[filename.rfind('/')+1:]
    filename = filename[filename.rfind("\\")+1:]
    if len(fname) > len(fnam2):
        fname += "        "
        fname = fname[0:(len(fnam2) + 8)]
        fnam2 += " %7s" % filename
    else:
        fnam2 += "        "
        fnam2 = fnam2[0:(len(fname) + 8)]
        fname += " %7s" % filename
    if len(ratio) > len(rat2):
        ratio += "        "
        ratio = ratio[0:(len(rat2) + 8)]
        rat2  += " %7s" % ("%d:%d" % (htest, stest))
    else:
        rat2  += "        "
        rat2  = rat2[0:(len(ratio) + 8)]
        ratio += " %7s" % ("%d:%d" % (htest, stest))
    fptot += "%8d"   % fp
    fpper += "%8.2f" % fpp
    fntot += "%8d"   % fn
    fnper += "%8.2f" % fnp
    untot += "%8d"   % un
    unper += "%8.2f" % unp
    rcost += "%8s"   % ("$%.2f" % cost)
    bcost += "%8s"   % ("$%.2f" % bestcost)
    hmean += "%8.2f" % hamdevall[0]
    hsdev += "%8.2f" % hamdevall[1]
    smean += "%8.2f" % spamdevall[0]
    ssdev += "%8.2f" % spamdevall[1]
    meand += "%8.2f" % (spamdevall[0] - hamdevall[0])
    k = (spamdevall[0] - hamdevall[0]) / (spamdevall[1] + hamdevall[1])
    kval  += "%8.2f" % k

print fname
if len(fnam2.strip()) > 0:
    print fnam2
print ratio
if len(rat2.strip()) > 0:
    print rat2
print fptot
print fpper
print fntot
print fnper
print untot
print unper
print rcost
print bcost
print hmean
print hsdev
print smean
print ssdev
print meand
print kval
