#!/usr/bin/env python

"""
rebal.py - rebalance a ham or spam directory, moving files to or from
a reservoir directory as necessary.

usage: rebal.py [ options ]
options:
   -r res - specify an alternate reservoir [%(RESDIR)s]
   -s set - specify an alternate Set pfx [%(SETPFX)s]
   -n num - specify number of files per dir [%(NPERDIR)s]
   -v     - tell user what's happening [%(VERBOSE)s]
   -q     - be quiet about what's happening [not %(VERBOSE)s]
   -c     - confirm file moves into Set directory [%(CONFIRM)s]
   -Q     - be quiet and don't confirm moves

The script will work with a variable number of Set directories, but they
must already exist.

Example:

    rebal.py -r reservoir -s Set -n 300

This will move random files between the directory 'reservoir' and the
various subdirectories prefixed with 'Set', making sure no more than 300
files are left in the 'Set' directories when finished.

Example:

Suppose you want to shuffle your Set files around, winding up with 300 files
in each one, you can execute:

    rebal.py -n 0
    rebal.py -n 300

The first run will move all files from the various Data/Ham/Set directories
to the Data/Ham/reservoir directory.  The second run will randomly parcel
out 300 files to each of the Data/Ham/Set directories.
"""

import os
import sys
import random
import glob
import getopt

# defaults
NPERDIR = 4000
RESDIR = 'Data/Ham/reservoir'
SETPFX = 'Data/Ham/Set'
VERBOSE = True
CONFIRM = True

def usage():
    print >> sys.stderr, """\
usage: rebal.py [ options ]
options:
   -r res - specify an alternate reservoir [%(RESDIR)s]
   -s set - specify an alternate Set pfx [%(SETPFX)s]
   -n num - specify number of files per dir [%(NPERDIR)s]
   -v     - tell user what's happening [%(VERBOSE)s]
   -q     - be quiet about what's happening [not %(VERBOSE)s]
   -c     - confirm file moves into Set directory [%(CONFIRM)s]
   -Q     - be quiet and don't confirm moves
""" % globals()

def migrate(f, dir, verbose):
    """rename f into dir, making sure to avoid name clashes."""
    base = os.path.split(f)[-1]
    out = os.path.join(dir, base)
    while os.path.exists(out):
        basename, ext = os.path.splitext(base)
        digits = random.randrange(100000000)
        out = os.path.join(dir, str(digits) + ext)
    if verbose:
        print "moving", f, "to", out
    os.rename(f, out)

def main(args):
    nperdir = NPERDIR
    resdir = RESDIR
    setpfx = SETPFX
    verbose = VERBOSE
    confirm = CONFIRM

    try:
        opts, args = getopt.getopt(args, "r:s:n:vqcQh")
    except getopt.GetoptError:
        usage()
        return 1

    for opt, arg in opts:
        if opt == "-n":
            nperdir = int(arg)
        elif opt == "-r":
            resdir = arg
        elif opt == "-s":
            setpfx = arg
        elif opt == "-v":
            verbose = True
        elif opt == "-c":
            confirm = True
        elif opt == "-q":
            verbose = False
        elif opt == "-Q":
            verbose = confirm = False
        elif opt == "-h":
            usage()
            return 0

    res = os.listdir(resdir)

    dirs = glob.glob(setpfx+"*")
    if dirs == []:
        print >> sys.stderr, "no directories beginning with", setpfx, "exist."
        return 1

    stuff = []
    n = len(res)
    for dir in dirs:
        fs = os.listdir(dir)
        n += len(fs)
        stuff.append((dir, fs))

    if nperdir * len(dirs) > n:
        print >> sys.stderr, "not enough files to go around - use lower -n."
        return 1

    # weak check against mixing ham and spam
    if ("Ham" in setpfx and "Spam" in resdir or
        "Spam" in setpfx and "Ham" in resdir):
        yn = raw_input("Reservoir and Set dirs appear not to match. "
                       "Continue? (y/n) ")
        if yn.lower()[0:1] != 'y':
            return 1

    # if necessary, migrate random files to the reservoir
    for (dir, fs) in stuff:
        if nperdir >= len(fs):
            continue

        random.shuffle(fs)
        movethese = fs[nperdir:]
        del fs[nperdir:]
        for f in movethese:
            migrate(os.path.join(dir,f), resdir, verbose)
        res.extend(movethese)

    # randomize reservoir once so we can just bite chunks from the front
    random.shuffle(res)

    # grow Set* directories from the reservoir
    for (dir, fs) in stuff:
        if nperdir == len(fs):
            continue

        movethese = res[:nperdir-len(fs)]
        res = res[nperdir-len(fs):]
        for f in movethese:
            if confirm:
                print file(os.path.join(resdir,f)).read()
                ok = raw_input('good enough? ').lower()
                if not ok.startswith('y'):
                    continue
            migrate(os.path.join(resdir,f), dir, verbose)
        fs.extend(movethese)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
