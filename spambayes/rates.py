"""
rates.py basename

Assuming that file

    basename + '.txt'

contains output from timtest.py, scans that file for summary statistics,
displays them to stdout, and also writes them to file

    basename + 's.txt'

(where the 's' means 'summary').  This doesn't need a full output file, and
will display stuff for as far as the output file has gotten so far.

Two of these summary files can later be fed to cmp.py.
"""

import re
import sys

"""
Training on Data/Ham/Set1 & Data/Spam/Set1 ... 4000 hams & 2750 spams
    testing against Data/Ham/Set2 & Data/Spam/Set2 ... 4000 hams & 2750 spams
    false positive: 0.025
    false negative: 1.34545454545
    new false positives: ['Data/Ham/Set2/66645.txt']
"""
pat1 = re.compile(r'\s*Training on Data/').match
pat2 = re.compile(r'\s+false (positive|negative): (.*)').match
pat3 = re.compile(r"\s+new false (positives|negatives): \[(.+)\]").match

def doit(basename):
    ifile = file(basename + '.txt')
    oname = basename + 's.txt'
    ofile = file(oname, 'w')
    print basename, '->', oname

    def dump(*stuff):
        msg = ' '.join(map(str, stuff))
        print msg
        print >> ofile, msg

    nfn = nfp = 0
    ntrainedham = ntrainedspam = 0
    for line in ifile:
        "Training on Data/Ham/Set1 & Data/Spam/Set1 ... 4000 hams & 2750 spams"
        m = pat1(line)
        if m:
            dump(line[:-1])
            fields = line.split()
            ntrainedham += int(fields[-5])
            ntrainedspam += int(fields[-2])
            continue

        "false positive: 0.025"
        "false negative: 1.34545454545"
        m = pat2(line)
        if m:
            kind, guts = m.groups()
            guts = float(guts)
            if kind == 'positive':
                lastval = guts
            else:
                dump('    %7.3f %7.3f' % (lastval, guts))
            continue

        "new false positives: ['Data/Ham/Set2/66645.txt']"
        m = pat3(line)
        if m:   # note that it doesn't match at all if the list is "[]"
            kind, guts = m.groups()
            n = len(guts.split())
            if kind == 'positives':
                nfp += n
            else:
                nfn += n

    dump('total false pos', nfp, nfp * 1e2 / ntrainedham)
    dump('total false neg', nfn, nfn * 1e2 / ntrainedspam)

for name in sys.argv[1:]:
    doit(name)
