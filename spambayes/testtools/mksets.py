#! /usr/bin/env python

### Redistribute messages among the classic Data/*/Set* directories
### based on desired set count, desired with messages
### directories based from MH mailboxes ~/Mail/everything and
### ~/Mail/spam.

"""Usage: %(program)s [OPTIONS] ...

Where OPTIONS is one or more of:
    -h
        show usage and exit
    -s num
        random number seed
    -n num
        number of sets
    -g num
        number of groups
    -m num
        number of messages per {ham,spam}*group*set
"""

import getopt
import sys
import os
import os.path
import glob
import shutil
import random

program = sys.argv[0]
loud = True
hamdir = "Data/Ham"
spamdir = "Data/Spam"
nsets = 5
ngroups = None
nmess = None

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def bybasename(a, b):
    return cmp(os.path.basename(a).split("-", 2)[0],
               os.path.basename(b).split("-", 2)[0])

def distribute(dir):
    files = glob.glob(os.path.join(dir, "*", "*"))
    random.shuffle(files)
    files.sort(bybasename)

    trash = glob.glob(os.path.join(dir, "Set*"))
    for set in range(1, nsets + 1):
        name = os.path.join(dir, "Set%d" % set)
        try:
            os.makedirs(name)
        except:
            pass
        try:
            trash.remove(name)
        except:
            pass
    try:
        os.makedirs(os.path.join(dir, "reservoir"))
    except:
        pass

    oldgroup = ""
    cgroups = 0
    cmess = 0
    cset = 1
    for f in files:
        newgroup = (f.split('-'))[0]
        if newgroup != oldgroup:
            oldgroup = newgroup
            cgroups = cgroups + 1
            cmess = 0
        cmess = cmess + 1
        if ((ngroups is not None and cgroups > ngroups) or
            (nmess is not None and cmess > (nmess * nsets))):
            newname = os.path.join(dir, "reservoir",
                                   os.path.basename(f))
        else:
            newname = os.path.join(dir, "Set%d" % cset,
                                   os.path.basename(f))
            cset = (cset % nsets) + 1
        sys.stdout.write("%-78s\r" % ("Moving %s to %s" % (f, newname)))
        sys.stdout.flush()
        if f != newname:
            os.rename(f, newname)

    for f in trash:
        os.rmdir(f)

def main():
    """Main program; parse options and go."""

    global loud
    global nsets
    global ngroups
    global nmess

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hs:n:g:m:')
    except getopt.error, msg:
        usage(2, msg)

    if opts:
        for opt, arg in opts:
            if opt == '-h':
                usage(0)
            elif opt == '-s':
                random.seed(int(arg))
            elif opt == '-n':
                nsets = int(arg)
            elif opt == '-g':
                ngroups = int(arg)
            elif opt == '-m':
                nmess = int(arg)
        if args:
            usage(2, "Positional arguments not allowed")

    distribute(hamdir)
    distribute(spamdir)
    print


if __name__ == "__main__":
    main()
