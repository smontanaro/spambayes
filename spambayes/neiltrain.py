#! /usr/bin/env python

"""Usage: %(program)s spam.mbox ham.mbox wordprobs.cdb
"""

import sys
import os
import mailbox
import email
import classifier
import cdb

program = sys.argv[0] # For usage(); referenced by docstring above

from tokenizer import tokenize

def getmbox(msgs):
    """Return an iterable mbox object"""
    def _factory(fp):
        try:
            return email.message_from_file(fp)
        except email.Errors.MessageParseError:
            return ''

    if msgs.startswith("+"):
        import mhlib
        mh = mhlib.MH()
        mbox = mailbox.MHMailbox(os.path.join(mh.getpath(), msgs[1:]),
                                 _factory)
    elif os.path.isdir(msgs):
        # XXX Bogus: use an MHMailbox if the pathname contains /Mail/,
        # else a DirOfTxtFileMailbox.
        if msgs.find("/Mail/") >= 0:
            mbox = mailbox.MHMailbox(msgs, _factory)
        else:
            mbox = DirOfTxtFileMailbox(msgs, _factory)
    else:
        fp = open(msgs)
        mbox = mailbox.PortableUnixMailbox(fp, _factory)
    return mbox

def train(bayes, msgs, is_spam):
    """Train bayes with all messages from a mailbox."""
    mbox = getmbox(msgs)
    for msg in mbox:
        bayes.learn(tokenize(msg), is_spam, False)

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    """Main program; parse options and go."""
    if len(sys.argv) != 4:
        usage(2)

    spam_name = sys.argv[1]
    ham_name = sys.argv[2]
    db_name = sys.argv[3]
    bayes = classifier.GrahamBayes()
    print 'Training with spam...'
    train(bayes, spam_name, True)
    print 'Training with ham...'
    train(bayes, ham_name, False)
    print 'Updating probabilities...'
    bayes.update_probabilities()
    items = []
    for word, winfo in bayes.wordinfo.iteritems():
        #print `word`, str(winfo.spamprob)
        items.append((word, str(winfo.spamprob)))
    print 'Writing DB...'
    db = open(db_name, "wb")
    cdb.cdb_make(db, items)
    db.close()
    print 'done'

if __name__ == "__main__":
    main()
