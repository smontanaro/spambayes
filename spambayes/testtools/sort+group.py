#! /usr/bin/env python

### Sort and group the messages in the Data hierarchy.
### Run this prior to mksets.py for setting stuff up for
### testing of chronological incremental training.

"""Usage: %(program)s

This program has no options!  Muahahahaha!
"""

import sys
import os
import getopt
import glob
import re
import time
import filecmp

program = sys.argv[0]
loud = True
day = 24 * 60 * 60
dates = {}

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def bydate(name1, name2):
    return cmp(dates[name1], dates[name2])

def main():
    """Main program; parse options and go."""

    global dates
    dates = {}
    names = []
    date_re = re.compile(
        r";[^0]* (\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{2,4})")
    now = time.mktime(time.strptime(time.strftime("%d %b %Y"), "%d %b %Y"))
    if loud: print "Scanning everything"
    for name in glob.glob('Data/*/*/*'):
        if loud:
            sys.stdout.write("%-78s\r" % name)
            sys.stdout.flush()
        fh = file(name, "rb")
        received = ""
        line = fh.readline()
        while line != "\r\n" and line != "\n" and line != "":
            if line.lower().startswith("received:"):
                received = line
                line = fh.readline()
                while line != "" and (line[0] == " " or line[0] == "\t"):
                    received += line
                    line = fh.readline()
                break
            line = fh.readline()
        fh.close()
        # Figure out how old the message is
        date = now
        try:
            log = str(received)
            received = date_re.search(received).group(1)
            log = "\n" + str(received)
            date = time.mktime(time.strptime(received, "%d %b %Y"))
        except:
            print "Couldn't parse " + name + ":"
            print log
            pass
        dates[name] = date
        names.append(name)
    if loud: print ""

    if loud: print "Sorting"
    names.sort(bydate)

    if loud: print "Renaming first pass"
    for name in names:
        dir = os.path.dirname(name)
        base = os.path.basename(name)
        os.rename(name, os.path.join(dir, "-"+base))

    if loud: print "Renaming second pass"
    first = dates[names[0]]
    for num in range(0, len(names)):
        name = names[num]
        dir = os.path.dirname(name)
        base = os.path.basename(name)
        group = int((dates[name] - first) // day)
        os.rename(os.path.join(dir, "-"+base),
                  os.path.join(dir, "%04d-%06d" % (group, num)))

if __name__ == "__main__":
    main()
