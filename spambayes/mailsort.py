#! /usr/bin/env python
"""\
To train:
    %(program)s -t ham.mbox spam.mbox

To filter mail (using .forward or .qmail):
    |%(program)s Maildir/ Mail/Spam/

To print the score and top evidence for a message or messages:
    %(program)s -s message [message ...]
"""

SPAM_CUTOFF = 0.57

SIZE_LIMIT = 5000000 # messages larger are not analyzed
BLOCK_SIZE = 10000
RC_DIR = "~/.spambayes"
DB_FILE = RC_DIR + "/wordprobs.cdb"
OPTION_FILE = RC_DIR + "/bayescustomize.ini"

import sys
import os
import getopt
import email
import time
import signal
import socket
import email

DB_FILE = os.path.expanduser(DB_FILE)
if not os.environ.has_key('BAYESCUSTOMIZE'):
    os.environ['BAYESCUSTOMIZE'] = os.path.expanduser(OPTION_FILE)

from spambayes import mboxutils
from spambayes.cdb_classifier import CdbClassifer
from spambayes.tokenizer import tokenize


try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


program = sys.argv[0] # For usage(); referenced by docstring above

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

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

def train(bayes, msgs, is_spam):
    """Train bayes with all messages from a mailbox."""
    mbox = mboxutils.getmbox(msgs)
    for msg in mbox:
        bayes.learn(tokenize(msg), is_spam)

def train_messages(ham_name, spam_name):
    """Create database using messages."""

    rc_dir = os.path.expanduser(RC_DIR)
    if not os.path.exists(rc_dir):
        print "Creating", RC_DIR, "directory..."
        os.mkdir(rc_dir)
    bayes = CdbClassifer()
    print 'Training with ham...'
    train(bayes, ham_name, False)
    print 'Training with spam...'
    train(bayes, spam_name, True)
    print 'Update probabilities and writing DB...'
    db = open(DB_FILE, "wb")
    bayes.save_wordinfo(db)
    db.close()
    print 'done'

def filter_message(hamdir, spamdir):
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
            bayes = CdbClassifer(open(DB_FILE, 'rb'))
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

def print_message_score(msg_name):
    msg = email.message_from_file(open(msg_name))
    bayes = CdbClassifer(open(DB_FILE, 'rb'))
    prob, evidence = bayes.spamprob(tokenize(msg), evidence=True)
    print msg_name, prob
    for word, prob in evidence:
        print '  ', `word`, prob

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'ts')
    except getopt.error, msg:
        usage(2, msg)

    if len(opts) > 1:
        usage(2, 'conflicting options')

    if not opts:
        if len(args) != 2:
            usage(2, 'wrong number of arguments')
        filter_message(args[0], args[1])
    elif opts[0][0] == '-t':
        if len(args) != 2:
            usage(2, 'wrong number of arguments')
        train_messages(args[0], args[1])
    elif opts[0][0] == '-s':
        for msg in args:
            print_message_score(msg)
    else:
        raise RuntimeError # shouldn't get here
    
    
if __name__ == "__main__":
    main()
