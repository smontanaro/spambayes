#! /usr/bin/env python

### Sort and group the messages in the Data hierarchy.
### Run this prior to mksets.py for setting stuff up for
### testing of chronological incremental training.

"""Usage: sort+group.py

This program has no options!  Muahahahaha!
"""

import sys
import os
import glob
import time

from email.Utils import parsedate_tz, mktime_tz

loud = True
SECONDS_PER_DAY = 24 * 60 * 60

# Scan the file with path fpath for its first Received header, and return
# a UTC timestamp for the date-time it specifies.  If anything goes wrong
# (can't find a Received header; can't parse the date), return None.
# This is the best guess about when we received the msg.
def get_time(fpath):
    fh = file(fpath, 'rb')
    lines = iter(fh)
    # Find first Received header.
    for line in lines:
        if line.lower().startswith("received:"):
            break
    else:
        print "\nNo Received header found."
        fh.close()
        return None
    # Paste on continuation lines, if any.
    received = line
    for line in lines:
        if line[0] in ' \t':
            received += line
        else:
            break
    fh.close()
    # RFC 2822 says the date-time field must follow a semicolon at the end.
    i = received.rfind(';')
    if i < 0:
        print "\n" + received
        print "No semicolon found in Received header."
        return None
    # We only want the part after the semicolon.
    datestring = received[i+1:]
    # It may still be split across lines (like "Wed, \r\n\t22 Oct ...").
    datestring = ' '.join(datestring.split())
    as_tuple = parsedate_tz(datestring)
    if as_tuple is None:
        print "\n" + received
        print "Couldn't parse the date: %r" % datestring
        return None
    return mktime_tz(as_tuple)

def main():
    """Main program; parse options and go."""

    from os.path import join, split

    data = []   # list of (time_received, dirname, basename) triples
    if loud:
        print "Scanning everything"
    now = time.time()
    for name in glob.glob('Data/*/*/*'):
        if loud:
            sys.stdout.write("%-78s\r" % name)
            sys.stdout.flush()
        when_received = get_time(name) or now
        data.append((when_received,) + split(name))

    if loud:
        print ""
        print "Sorting ..."
    data.sort()

    # First rename all the files to a form we can't produce in the end.
    # This is to protect against name clashes in case the files are
    # already named according to the scheme we use.
    if loud:
        print "Renaming first pass ..."
    for dummy, dirname, basename in data:
        os.rename(join(dirname, basename),
                  join(dirname, "-" + basename))

    if loud:
        print "Renaming second pass ..."
    earliest = data[0][0]  # timestamp of earliest msg received
    i = 0
    for when_received, dirname, basename in data:
        extension = os.path.splitext(basename)[-1]
        group = int((when_received - earliest) / SECONDS_PER_DAY)
        newbasename = "%04d-%06d" % (group, i)
        os.rename(join(dirname, "-" + basename),
                  join(dirname, newbasename + extension))
        i += 1

if __name__ == "__main__":
    main()
