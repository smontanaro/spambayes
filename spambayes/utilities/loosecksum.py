#!/usr/local/bin/python

"""
Compute a 'loose' checksum on the msg (file on cmdline or via stdin).

Attempts are made to eliminate content which tends to obscure the 'sameness'
of messages.  This is aimed particularly at spam, which tends to contains
lots of small differences across messages to try and thwart spam filters, in
hopes that at least one copy reaches its desitination.

Before calculating the checksum, this script does the following:

    * delete the message header

    * delete HTML tags which generally contain URLs

    * delete anything which looks like an email address or URL

    * finally, discard everything other than ascii letters and digits (note
      that this will almost certainly be ineffectual for spam written in
      eastern languages such as Korean)

An MD5 checksum is then computed for the resulting text and written to stdout.

"""

import getopt
import sys
import re
import binascii

from spambayes.mboxutils import getmbox
from spambayes.port import md5

def flatten(obj):
    # I do not know how to use the email package very well - all I want here
    # is the body of obj expressed as a string - there is probably a better
    # way to accomplish this which I haven't discovered.
    # three types are possible: string, Message (hasattr(get_payload)), list
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "get_payload"):
        return flatten(obj.get_payload())
    if isinstance(obj, list):
        return "\n".join([flatten(b) for b in obj])
    raise TypeError, ("unrecognized body type: %s" % type(obj))

def generate_checksum(msg):
    data = flatten(msg)

    # modelled after Justin Mason's fuzzy checksummer for SpamAssassin.
    # Message body is cleaned, then broken into lines.  The list of lines is
    # then broken into four parts and separate checksums are generated for
    # each part.  They are then joined together with '.'.  Downstream
    # processes can split those chunks into pieces and consider them
    # separately or in various combinations if desired.

    # Get rid of anything which looks like an HTML tag and downcase it all
    data = re.sub(r"<[^>]*>", "", data).lower()

    # delete anything which looks like a url or email address
    # not sure what a pmguid: url is but it seems to occur frequently in spam
    words = [w for w in data.split(' ')
             if ('@' not in w and
                 (':' not in w or
                  w[:4] != "ftp:" and
                  w[:7] != "mailto:" and
                  w[:5] != "http:" and
                  w[:7] != "gopher:" and
                  w[:8] != "pmguid:"))]

    # delete lines which contain white space
    lines = [line for line in " ".join(words).split('\n') if ' ' in line]

    # +1 guarantees we don't miss lines at the end
    chunksize = len(lines)//4+1
    sum = []
    for i in range(4):
        chunk = "\n".join(lines[i*chunksize:(i+1)*chunksize])
        sum.append(binascii.b2a_hex(md5(chunk).digest()))

    return ".".join(sum)

def main(args):
    opts, args = getopt.getopt(args, "")
    for opt, arg in opts:
        pass
    if not args:
        mboxes = [getmbox("-")]
    else:
        mboxes = [getmbox(a) for a in args]

    for mbox in mboxes:
        for msg in mbox:
            print generate_checksum(msg)

if __name__ == "__main__":
    main(sys.argv[1:])
