#
# Optimize parameters
#
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

import sys

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

program = sys.argv[0]

default="""
[Classifier]
robinson_probability_x = 0.5
robinson_minimum_prob_strength = 0.1
robinson_probability_s = 0.45
max_discriminators = 150

[TestDriver]
spam_cutoff = 0.90
ham_cutoff = 0.20
"""

import Options

start = (Options.options.robinson_probability_x,
         Options.options.robinson_minimum_prob_strength,
         Options.options.robinson_probability_s,
         Options.options.spam_cutoff,
         Options.options.ham_cutoff)
err = (0.01, 0.01, 0.01, 0.005, 0.01)

def mkini(vars):
    f=open('bayescustomize.ini', 'w')
    f.write("""
[Classifier]
robinson_probability_x = %.6f
robinson_minimum_prob_strength = %.6f
robinson_probability_s = %.6f

[TestDriver]
spam_cutoff = %.4f
ham_cutoff = %.4f
"""%tuple(vars))
    f.close()

def score(vars):
    import os
    mkini(vars)
    status = os.system('python2.3 weaktest.py -n %d > weak.out'%nsets)
    if status != 0:
        print >> sys.stderr, "Error status from weaktest"
        sys.exit(status)
    f = open('weak.out', 'r')
    txt = f.readlines()
    # Extract the flex cost field.
    cost = float(txt[-1].split()[2][1:])
    f.close()
    print ''.join(txt[-4:])[:-1]
    print "x=%.4f p=%.4f s=%.4f sc=%.3f hc=%.3f %.2f"%(tuple(vars)+(cost,))
    return -cost

def main():
    import optimize
    finish=optimize.SimplexMaximize(start,err,score)
    mkini(finish)

if __name__ == "__main__":
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

    main()
