#!/usr/bin/env python

"""
rebal.py - rebalance a ham or spam test directory

usage: rebal.py [ options ]
options:
   -d     - dry run; display what would be moved, but don't do it [%(DRYRUN)s]
   -r res - specify an alternate reservoir [%(RESDIR)s]
   -s set - specify an alternate Set prefix [%(SETPREFIX)s]
   -n num - specify number of files per Set dir desired [%(NPERDIR)s]
   -v     - tell user what's happening [%(VERBOSE)s]
   -q     - be quiet about what's happening [not %(VERBOSE)s]
   -c     - confirm file moves into Set directory [%(CONFIRM)s]
   -Q     - don't confirm moves; this is independent of -v/-q
   -h     - display this message and quit

Moves files among the Set subdirectories and a reservoir directory as
necessary.  You should execute this script from the directory containing your
Data directory.  By default, the Set1, Set2, ..., and reservoir subdirectories
under (relative path) Data/Ham/ are rebalanced; this can be changed with the
-s argument.  The script will work with a variable number of Set directories,
but they must already exist, and the reservoir directory must also exist.

It's recommended that you run with the -d (dry run) option first, to see what
the script would do without actually moving any files.  If, e.g., you
accidentally mix up spam Sets with your Ham reservoir, it could be very
difficult to recover from that mistake.

Example:

    rebal.py -r reservoir -s Set -n 300

This will move random files between the directory 'reservoir' and the
various subdirectories prefixed with 'Set', making sure no more than 300
files are left in the 'Set' directories when finished.

Example:

Suppose you want to shuffle your Set files around, winding up with 300 files
in each one, you can execute:

    rebal.py -n 0
    rebal.py -n 300 -Q

The first run will move all files from the various Data/Ham/Set directories
to the Data/Ham/reservoir directory.  The second run will randomly parcel
out 300 files to each of the Data/Ham/Set directories.
"""

import os
import sys
import random
import glob
import getopt

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


# defaults
NPERDIR = 4000
RESDIR = 'Data/Ham/reservoir'
SETPREFIX = 'Data/Ham/Set'
VERBOSE = True
CONFIRM = True
DRYRUN = False

def usage(msg=None):
    if msg:
        print >> sys.stderr, str(msg)
    print >> sys.stderr, __doc__ % globals()

def migrate(f, targetdir, verbose):
    """Move f into targetdir, renaming if needed to avoid name clashes.

       The basename of the moved file is returned; this may not be the
       same as the basename of f, if the file had to be renamed because
       a file with f's basename already existed in targetdir.
    """

    base = os.path.split(f)[-1]
    out = os.path.join(targetdir, base)
    while os.path.exists(out):
        basename, ext = os.path.splitext(base)
        digits = random.randrange(100000000)
        out = os.path.join(targetdir, str(digits) + ext)
    if verbose:
        print "moving", f, "to", out
    os.rename(f, out)
    return os.path.split(f)[-1]

def main(args):
    nperdir = NPERDIR
    resdir = RESDIR
    setprefix = SETPREFIX
    verbose = VERBOSE
    confirm = CONFIRM
    dryrun = DRYRUN

    try:
        opts, args = getopt.getopt(args, "dr:s:n:vqcQh")
    except getopt.GetoptError, msg:
        usage(msg)
        return 1

    for opt, arg in opts:
        if opt == "-n":
            nperdir = int(arg)
        elif opt == "-r":
            resdir = arg
        elif opt == "-s":
            setprefix = arg
        elif opt == "-v":
            verbose = True
        elif opt == "-c":
            confirm = True
        elif opt == "-q":
            verbose = False
        elif opt == "-Q":
            confirm = False
        elif opt == "-d":
            dryrun = True
        elif opt == "-h":
            usage()
            return 0
        else:
            raise SystemError("internal error on option '%s'" % opt)

    res = os.listdir(resdir)

    dirs = glob.glob(setprefix + "*")
    if dirs == []:
        print >> sys.stderr, "no directories starting with", setprefix, "exist."
        return 1

    # stuff <- list of (directory, files) pairs, where directory is the
    # name of a Set subdirectory, and files is a list of files in that dir.
    stuff = []
    n = len(res)
    for d in dirs:
        fs = os.listdir(d)
        n += len(fs)
        stuff.append((d, fs))

    if nperdir * len(dirs) > n:
        print >> sys.stderr, "not enough files to go around - use lower -n."
        return 1

    # weak check against mixing ham and spam
    if ((setprefix.find("Ham") >= 0 and resdir.find("Spam") >= 0) or
        (setprefix.find("Spam") >= 0 and resdir.find("Ham") >= 0)):
        yn = raw_input("Reservoir and Set dirs appear not to match. "
                       "Continue? (y/n) ")
        if yn.lower()[0:1] != 'y':
            return 1

    # If necessary, migrate random files to the reservoir.
    for (d, fs) in stuff:
        if len(fs) <= nperdir:
            continue

        # Retain only nperdir files, moving the rest to reservoir.
        random.shuffle(fs)
        movethese = fs[nperdir:]
        del fs[nperdir:]
        if dryrun:
            print "would move", len(movethese), "files from", d, \
                  "to reservoir", resdir
            res.extend(movethese)
        else:
            for f in movethese:
                newname = migrate(os.path.join(d, f), resdir, verbose)
                res.append(newname)

    # Randomize reservoir once so we can just bite chunks from the end.
    random.shuffle(res)

    # Grow Set* directories from the reservoir as needed.
    for (d, fs) in stuff:
        assert len(fs) <= nperdir
        if nperdir == len(fs):
            continue

        numtomove = nperdir - len(fs)
        assert 0 < numtomove <= len(res)
        movethese = res[-numtomove:]
        del res[-numtomove:]
        if dryrun:
            print "would move", len(movethese), "files from reservoir", \
                  resdir, "to", d
        else:
            for f in movethese:
                if confirm:
                    print file(os.path.join(resdir, f)).read()
                    ok = raw_input('good enough? ').lower()
                    if not ok.startswith('y'):
                        continue
                migrate(os.path.join(resdir, f), d, verbose)

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
