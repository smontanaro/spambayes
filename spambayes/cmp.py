#!/usr/bin/env python

"""
cmp.py sbase1 sbase2

Combines output from sbase1.txt and sbase2.txt, which are created by
rates.py from timtest.py output, and displays comparison statistics to
stdout.
"""

import sys
f1n, f2n = sys.argv[1:3]

# Return
#  (list of all f-p rates,
#   list of all f-n rates,
#   total f-p,
#   total f-n,
#   average f-p rate,
#   average f-n rate)
# from summary file f.
def suck(f):
    fns = []
    fps = []
    get = f.readline
    while 1:
        line = get()
        if line.startswith('-> <stat> tested'):
            print line,
        if line.startswith('-> '):
            continue
        if line.startswith('total'):
            break
        # A line with an f-p rate and an f-n rate.
        p, n = map(float, line.split())
        fps.append(p)
        fns.append(n)

    # "total unique false pos 0"
    # "total unique false neg 0"
    # "average fp % 0.0"
    # "average fn % 0.0"
    fptot = int(line.split()[-1])
    fntot = int(get().split()[-1])
    fpmean = float(get().split()[-1])
    fnmean = float(get().split()[-1])
    return fps, fns, fptot, fntot, fpmean, fnmean

def tag(p1, p2):
        if p1 == p2:
            t = "tied"
        else:
            t = p1 < p2 and "lost " or "won  "
            if p1:
                p = (p2 - p1) * 100.0 / p1
                t += " %+7.2f%%" % p
            else:
                t += " +(was 0)"
        return t

def dump(p1s, p2s):
    alltags = ""
    for p1, p2 in zip(p1s, p2s):
        t = tag(p1, p2)
        print "    %5.3f  %5.3f  %s" % (p1, p2, t)
        alltags += t + " "
    print
    for t in "won", "tied", "lost":
        print "%-4s %2d times" % (t, alltags.count(t))
    print

def windowsfy(fn):
    import os
    if os.path.exists(fn + '.txt'):
        return fn + '.txt'
    else:
        return fn

print f1n, '->', f2n


f1n = windowsfy(f1n)
f2n = windowsfy(f2n)

fp1, fn1, fptot1, fntot1, fpmean1, fnmean1 = suck(file(f1n))
fp2, fn2, fptot2, fntot2, fpmean2, fnmean2 = suck(file(f2n))

print
print "false positive percentages"
dump(fp1, fp2)
print "total unique fp went from", fptot1, "to", fptot2, tag(fptot1, fptot2)
print "mean fp % went from", fpmean1, "to", fpmean2, tag(fpmean1, fpmean2)

print
print "false negative percentages"
dump(fn1, fn2)
print "total unique fn went from", fntot1, "to", fntot2, tag(fntot1, fntot2)
print "mean fn % went from", fnmean1, "to", fnmean2, tag(fnmean1, fnmean2)
