#! /usr/bin/env python
"""Determine best hamcutoff and spamcutoff values from timcv output.

Usage: %(program)s [options] [input filenames]

Where options are:

    -h
        display this message and exit

    -u unknown-cost
        The cost to you of an uncertain message (Default $0.20)

    -p fp-cost
        The cost to you of a false positive (Default $10)

    -n fn-cost
        The cost to you of a false negative (Default $1)

"""

import sys

# Defaults

unknowncost = 0.2
fpcost = 10
fncost = 1

program = sys.argv[0]

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def cost(spamhist,hamhist,hamcut,spamcut):
    spamok = 0
    spamunknown = 0
    spamnok = 0
    hamok = 0
    hamunknown = 0
    hamnok = 0
    for v, cnt in spamhist:
        if v < hamcut:
            spamnok += cnt
        elif v < spamcut:
            spamunknown += cnt
        else:
            spamok += cnt
    for v, cnt in hamhist:
        if v < hamcut:
            hamok += cnt
        elif v < spamcut:
            hamunknown += cnt
        else:
            hamnok += cnt
    #print hamok,hamunknown,hamnok
    #print spamok,spamunknown,spamnok
    _cost = ((spamunknown + hamunknown) * unknowncost +
             fpcost*hamnok + fncost*spamnok)
    #print "At %.1f, %.1f, cost=%.1f"%(hamcut,spamcut,_cost)
    return _cost

def main(fn):
    state = 0
    hamhist = []
    spamhist = []
    for line in open(fn):
        if state == 0:
            if line.startswith('-> <stat> Ham scores for all runs'):
                state = 1
        elif state == 1:
            if line.startswith('*'):
                state = 2
        elif state == 2:
            word = line.split()
            try:
                v = float(word[0])
                cnt = int(word[1])
                hamhist.append((v, cnt))
            except IndexError:
                state = 3
        elif state == 3:
            if line.startswith('*'):
                state = 4
        elif state == 4:
            word = line.split()
            try:
                v = float(word[0])
                cnt = int(word[1])
                spamhist.append((v, cnt))
            except ValueError:
                state = 5
    besthamcut = 50
    bestspamcut = 80
    bestcost = cost(spamhist, hamhist, besthamcut, bestspamcut)
    for hamcut in range(1, 90):
        sys.stdout.write(".")
        sys.stdout.flush()
        for spamcut in range(max(51, hamcut), 100):
            trial = cost(spamhist, hamhist, hamcut, spamcut)
            if trial <= bestcost:
                besthamcut = hamcut
                bestspamcut = spamcut
                bestcost = trial
    sys.stdout.write("\n")
    print "%s: Optimal cost is $%.1f with grey zone between %.1f and %.1f" % (
          fn, bestcost, besthamcut, bestspamcut)

if __name__=="__main__":
    import getopt

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'p:n:u:', [])
    except getopt.error, msg:
        usage(1, msg)

    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-p':
            fpcost = float(arg)
        elif opt == '-n':
            fncost = float(arg)
        elif opt == '-u':
            unknowncost = float(arg)

    if unknowncost >= fncost or unknowncost >= fpcost:
        raise ValueError("This program requires that unknowns are cheaper "
                         "than fp or fn")

    for fn in args:
        main(fn)
