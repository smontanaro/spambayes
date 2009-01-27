#!/usr/bin/env python

"""
A fuzzy checksum program based on a message posted to the spambayes list a
long time ago from Justin Mason of the SpamAssassin gang.  The basic idea is
that you dump stuff that can be obviously variable (email addresses and
such), compute several partial checksums over what remains, then compare
pieces against previous partial checksums to make a decision about a match.

Note that this concept can break down for small messages.  I only use it
downstream from Spambayes - after it's scored the message as spam:

:0
* ^X-Spambayes-Classification: (.*-)?spam
{
    ### this recipe gobbles items with matching body checksums (taken
    ### loosely to try and avoid obvious tricks)
    :0 W: cksum.lock
    | pycksum.py -v $HOME/tmp/cksum.cache 2>> $HOME/tmp/cksum.log

    ... further spam processing here

}

That reduces the risk of tossing out mail I'm actually interested in. ;-) I
run it in verbose mode and save the log message.  It catches a fair fraction
of duplicate spams, probably 3 out of every 4.  (Mail for several email
addresses funnels into skip@mojam.com.)
"""

# message on stdin
# cmdline arg is db file to store checksums

# exit status is designed to fit into procmail's idea of delivery - exiting
# with a 0 implies the message is a duplicate and the message is deemed
# delivered - exiting with a 1 implies the message hasn't been seen before

import getopt
import sys
import email.Parser
import email.generator

import anydbm
import re
import time
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from spambayes.port import md5

def clean(data):
    """Clean the obviously variable stuff from a chunk of data.

    The first (and perhaps only) use of this is to try and eliminate bits
    of data that keep multiple spam email messages from looking the same.
    """
    # Get rid of anything which looks like an HTML tag and downcase it all
    data = re.sub(r"<[^>]*>", "", data).lower()

    # Map all digits to '#'
    data = re.sub(r"[0-9]+", "#", data)

    # Map a few common html entities
    data = re.sub(r"(&nbsp;)+", " ", data)
    data = re.sub(r"&lt;", "<", data)
    data = re.sub(r"&gt;", ">", data)
    data = re.sub(r"&amp;", "&", data)

    # Elide blank lines and multiple horizontal whitespace
    data = re.sub(r"\n+", "\n", data)
    data = re.sub(r"[ \t]+", " ", data)

    # delete anything which looks like a url or email address
    # not sure what a pmguid: url is but it seems to occur frequently in spam
    # also convert all runs of whitespace into a single space
    return " ".join([w for w in data.split(" ")
                     if ('@' not in w and
                         (':' not in w or
                          w[:4] != "ftp:" and
                          w[:7] != "mailto:" and
                          w[:5] != "http:" and
                          w[:7] != "gopher:" and
                          w[:8] != "pmguid:"))])

def generate_checksum(msg):
    # modelled after Justin Mason's fuzzy checksummer for SpamAssassin.
    # Message body is cleaned, then broken into lines.  The list of lines is
    # then broken into four parts and separate checksums are generated for
    # each part.  They are then joined together with '.'.  Downstream
    # processes can split those chunks into pieces and consider them
    # separately or in various combinations if desired.

    fp = StringIO.StringIO()
    g = email.generator.Generator(fp, mangle_from_=False, maxheaderlen=60)
    g.flatten(msg)
    text = fp.getvalue()
    body = text.split("\n\n", 1)[1]
    lines = clean(body).split("\n")
    chunksize = len(lines)//4+1
    digest = []
    for i in range(4):
        chunk = "\n".join(lines[i*chunksize:(i+1)*chunksize])
        digest.append(md5(chunk).hexdigest())

    return ".".join(digest)

def save_checksum(cksum, f):
    pieces = cksum.split('.')
    result = 1
    db = anydbm.open(f, "c")
    maxdblen = 2**14
    # consider the first two pieces, the middle two pieces and the last two
    # pieces - one or more will likely eliminate attempts at disrupting the
    # checksum - if any are found in the db file, call it a match
    for subsum in (".".join(pieces[:-2]),
                   ".".join(pieces[1:-1]),
                   ".".join(pieces[2:])):
        if not db.has_key(subsum):
            db[subsum] = str(time.time())
            if len(db) > maxdblen:
                items = [(float(db[k]), k) for k in db.keys()]
                items.sort()
                # the -20 brings us down a bit below the max so we aren't
                # constantly running this chunk of code
                items = items[:-(maxdblen-20)]
                for v, k in items:
                    del db[k]
        else:
            result = 0
            break
    db.close()
    return result

def main(args):
    opts, args = getopt.getopt(args, "v")
    verbose = 0
    for opt, arg in opts:
        if opt == "-v":
            verbose = 1

    if not args:
        dbf = None
    else:
        dbf = args[0]

    msg = email.Parser.Parser().parse(sys.stdin)
    cksum = generate_checksum(msg)
    if dbf is None:
        print cksum
        result = 1
        disp = 'nodb'
    else:
        result = save_checksum(cksum, dbf)
        disp = result and 'old' or 'new'

    if verbose:
        t = time.strftime("%Y-%m-%d:%H:%M:%S", time.localtime(time.time()))
        logmsg = "%s/%s/%s/%s\n" % (t, cksum, disp, msg['message-id'])
        sys.stderr.write(logmsg)

    return result

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
