"""
cmp.py sbase1 sbase2

Combines output from sbase1.txt and sbase2.txt, which are created by
rates.py from timtest.py output, and displays comparison statistics to
stdout.
"""

import sys
f1n, f2n = sys.argv[1:3]

NSETS = 5

# Return
#  (list of all f-p rates,
#   list of all f-n rates,
#   total f-p,
#   total f-n)
# from summary file f.
def suck(f):
    fns = []
    fps = []
    for block in range(NSETS):
        # Skip, e.g.,
        # Training on Data/Ham/Set1 & Data/Spam/Set1 ... 4000 hams & 2750 spams
        f.readline()
        for inner in range(NSETS - 1):
            # A line with an f-p rate and an f-n rate.
            p, n = map(float, f.readline().split())
            fps.append(p)
            fns.append(n)

    # "total false pos 8 0.04"
    # "total false neg 249 1.81090909091"
    fptot = int(f.readline().split()[-2])
    fntot = int(f.readline().split()[-2])
    return fps, fns, fptot, fntot

def dump(p1s, p2s):
    alltags = ""
    for p1, p2 in zip(p1s, p2s):
        if p1 < p2:
            tag = "lost"
        elif p1 > p2:
            tag = "won"
        else:
            tag = "tied"
        print "    %5.3f  %5.3f  %s" % (p1, p2, tag)
        alltags += tag + " "
    print
    for tag in "won", "tied", "lost":
        print "%-4s %2d %s" % (tag, alltags.count(tag), "times")
    print

fp1, fn1, fptot1, fntot1 = suck(file(f1n + '.txt'))
fp2, fn2, fptot2, fntot2 = suck(file(f2n + '.txt'))

print f1n, '->', f2n

print
print "false positive percentages"
dump(fp1, fp2)
print "total unique fp went from", fptot1, "to", fptot2

print
print "false negative percentages"
dump(fn1, fn2)
print "total unique fn went from", fntot1, "to", fntot2
