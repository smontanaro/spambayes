#! /usr/bin/env python

# Redistribute messages among the classic Data/{Ham,Spam}/Set* directories,
# based on desired set count.

"""Usage: %(program)s [OPTIONS] ...

Where OPTIONS is one or more of:
    -h
        show usage and exit
    -n num
        number of sets; default 5
    -g num
        max number of groups; default unlimited
    -m num
        max number of messages per {ham,spam}*group*set; default unlimited
"""

import getopt
import sys
import os
import os.path
import glob
import shutil

program = sys.argv[0]
loud = True
hamdir = "Data/Ham"
spamdir = "Data/Spam"
nsets = 5               # -n
ngroups = None          # -g
nmess = None            # -m

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def distribute(dir):
    files = glob.glob(os.path.join(dir, "*", "*"))
    # Sort by time received, earliest first.  The base names must be such
    # that sorting by basename accomplishes this; that's true if
    # sort+group.py was run first.
    files = [(os.path.basename(f), f) for f in files]
    files.sort()
    files = [t[-1] for t in files]

    # Make sure all the desired Set directories exist, and a reservoir
    # directory.  "trash" is left holding a list of the excess Set
    # directories (if nsets is less than the number of Set directories
    # that already exist).  Those directories will be removed at the
    # end, after all the messages they contain have been moved elsewhere.
    trash = glob.glob(os.path.join(dir, "Set*"))
    for subdir in ["Set%d" % i for i in range(1, nsets+1)] + ["reservoir"]:
        name = os.path.join(dir, subdir)
        try:
            os.makedirs(name)
        except:
            pass
        try:
            trash.remove(name)
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
        opts, args = getopt.getopt(sys.argv[1:], 'hn:g:m:')
    except getopt.error, msg:
        usage(2, msg)

    if args:
        usage(2, "Positional arguments not allowed")

    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-n':
            nsets = int(arg)
        elif opt == '-g':
            ngroups = int(arg)
        elif opt == '-m':
            nmess = int(arg)

    distribute(hamdir)
    distribute(spamdir)
    print


if __name__ == "__main__":
    main()
