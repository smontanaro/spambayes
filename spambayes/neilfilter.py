#! /usr/bin/env python

"""Usage: %(program)s wordprobs.cdb Maildir Spamdir
"""

import sys
import os
import time
import signal
import socket
import email
import cdb
from tokenizer import tokenize
import classifier

program = sys.argv[0] # For usage(); referenced by docstring above

BLOCK_SIZE = 10000
SIZE_LIMIT = 5000000 # messages larger are not analyzed
SPAM_CUTOFF = 0.57

class CdbWrapper(cdb.Cdb):
    def get(self, key, default=None,
            cdb_get=cdb.Cdb.get,
            WordInfo=classifier.WordInfo):
        prob = cdb_get(self, key, default)
        if prob is None:
            return None
        else:
            return WordInfo(0, float(prob))

class CdbBayes(classifier.Bayes):
    def __init__(self, cdbfile):
        classifier.Bayes.__init__(self)
        self.wordinfo = CdbWrapper(cdbfile)

def maketmp(dir):
    hostname = socket.gethostname()
    pid = os.getpid()
    fd = -1
    for x in xrange(200):
        filename = "%d.%d.%s" % (time.time(), pid, hostname)
        pathname = "%s/tmp/%s" % (dir, filename)
        try:
            fd = os.open(pathname, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0600)
        except IOError, exc:
            if exc[i] not in (errno.EINT, errno.EEXIST):
                raise
        else:
            break
        time.sleep(2)
    if fd == -1:
        raise SystemExit, "could not create a mail file"
    return (os.fdopen(fd, "wb"), pathname, filename)

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    if len(sys.argv) != 4:
        usage(2)

    wordprobfilename = sys.argv[1]
    hamdir = sys.argv[2]
    spamdir = sys.argv[3]

    signal.signal(signal.SIGALRM, lambda s: sys.exit(1))
    signal.alarm(24 * 60 * 60)

    # write message to temporary file (must be on same partition)
    tmpfile, pathname, filename = maketmp(hamdir)
    try:
        tmpfile.write(os.environ.get("DTLINE", "")) # delivered-to line
        bytes = 0
        blocks = []
        while 1:
            block = sys.stdin.read(BLOCK_SIZE)
            if not block:
                break
            bytes += len(block)
            if bytes < SIZE_LIMIT:
                blocks.append(block)
            tmpfile.write(block)
        tmpfile.close()

        if bytes < SIZE_LIMIT:
            msgdata = ''.join(blocks)
            del blocks
            msg = email.message_from_string(msgdata)
            del msgdata
            bayes = CdbBayes(open(wordprobfilename, 'rb'))
            prob = bayes.spamprob(tokenize(msg))
        else:
            prob = 0.0

        if prob > SPAM_CUTOFF:
            os.rename(pathname, "%s/new/%s" % (spamdir, filename))
        else:
            os.rename(pathname, "%s/new/%s" % (hamdir, filename))
    except:
        os.unlink(pathname)
        raise

if __name__ == "__main__":
    main()
