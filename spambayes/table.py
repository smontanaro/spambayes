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
            print line,
            htest = int(line.split()[3])
            stest = int(line.split()[6])
        if line.find(' items; mean ') != -1:
            # -> <stat> Ham distribution for this pair: 1000 items; mean 0.05; sample sdev 0.68
            # and later "sample " went away
            vals = line.split(';')
            mean = float(vals[1].split()[-1])
            sdev = float(vals[2].split()[-1])
            val = (mean, sdev)
            typ = vals[0].split()[2]
            if line.find('for all runs') != -1:
                if typ == 'Ham':
                    hamdevall = val
                else:
                    spamdevall = val
            continue
        if line.startswith('-> best cost for all runs: $'):
            bestcost = float(line.split('$')[-1])
        if line.startswith('-> <stat> all runs false positives: '):
            fp = int(line.split()[-1])
        if line.startswith('-> <stat> all runs false negatives: '):
            fn = int(line.split()[-1])
        if line.startswith('-> <stat> all runs unsure: '):
            un = int(line.split()[-1])
        if line.startswith('-> <stat> all runs false positive %: '):
            fpp = float(line.split()[-1])
        if line.startswith('-> <stat> all runs false negative %: '):
            fnp = float(line.split()[-1])
        if line.startswith('-> <stat> all runs unsure %: '):
            unp = float(line.split()[-1])
        if line.startswith('-> <stat> all runs cost: '):
            cost = float(line.split('$')[-1])
            break
        if line.startswith('-> '):
            continue

    return (htest, stest, fp, fn, un, fpp, fnp, unp, cost, bestcost,
            hamdevall, spamdevall)

def windowsfy(fn):
    import os
    if os.path.exists(fn + '.txt'):
        return fn + '.txt'
    else:
        return fn

ratio = "ham:spam: "
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
    ratio += "%8s" % ("%d:%d" % (htest, stest))
    fptot += "%8d" % fp
    fpper += "%8.2f" % fpp
    fntot += "%8d" % fn
    fnper += "%8.2f" % fnp
    untot += "%8d" % un
    unper += "%8.2f" % unp
    rcost += "%8s" % ("$%.2f" % cost)
    bcost += "%8s" % ("$%.2f" % bestcost)
    hmean += "%8.2f" % hamdevall[0]
    hsdev += "%8.2f" % hamdevall[1]
    smean += "%8.2f" % spamdevall[0]
    ssdev += "%8.2f" % spamdevall[1]
    meand += "%8.2f" % (spamdevall[0] - hamdevall[0])
    k = (spamdevall[0] - hamdevall[0]) / (spamdevall[1] + hamdevall[1])
    kval  += "%8.2f" % k

print ratio
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
