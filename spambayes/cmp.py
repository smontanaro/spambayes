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
#   total f-n)
# from summary file f.
def suck(f):
    fns = []
    fps = []
    while 1:
        line = f.readline()
        if line.startswith('total'):
            break
        if not line.startswith('Training'):
            # A line with an f-p rate and an f-n rate.
            p, n = map(float, line.split())
            fps.append(p)
            fns.append(n)

    # "total false pos 8 0.04"
    # "total false neg 249 1.81090909091"
    fptot = int(line.split()[-2])
    fntot = int(f.readline().split()[-2])
    return fps, fns, fptot, fntot

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
