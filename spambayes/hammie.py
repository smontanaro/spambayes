#! /usr/bin/env python

# A driver for the classifier module.  Currently mostly a wrapper around
# existing stuff.

"""Usage: %(program)s [options]

Where:
    -h
        show usage and exit
    -g PATH
        mbox or directory of known good messages (non-spam)
    -s PATH
        mbox or directory of known spam messages
    -p FILE
        use file as the persistent store.  loads data from this file if it
        exists, and saves data to this file at the end.  Default: hammie.db
    -d
        use the DBM store instead of cPickle.  The file is larger and
        creating it is slower, but checking against it is much faster,
        especially for large word databases.
    -f
        run as a filter: read a single message from stdin, add an
        X-Spam-Disposition header, and write it to stdout.
"""

from __future__ import generators

import sys
import os
import getopt
import mailbox
import glob
import email
import classifier
import errno
import anydbm
import cPickle as pickle

program = sys.argv[0]

# Tim's tokenizer kicks far more booty than anything I would have
# written.  Score one for analysis ;)
from timtoken import tokenize

class DBDict:
    """Database Dictionary

    This wraps an anydbm to make it look even more like a dictionary.

    Call it with the name of your database file.  Optionally, you can
    specify a list of keys to skip when iterating.  This only affects
    iterators; things like .keys() still list everything.  For instance:

    >>> d = DBDict('/tmp/goober.db', ('skipme', 'skipmetoo'))
    >>> d['skipme'] = 'booga'
    >>> d['countme'] = 'wakka'
    >>> print d.keys()
    ['skipme', 'countme']
    >>> for k in d.iterkeys():
    ...     print k
    countme

    """
    
    def __init__(self, dbname, iterskip=()):
        self.hash = anydbm.open(dbname, 'c')
        self.iterskip = iterskip

    def __getitem__(self, key):
        if self.hash.has_key(key):
            return pickle.loads(self.hash[key])
        else:
            raise KeyError(key)

    def __setitem__(self, key, val): 
        v = pickle.dumps(val, 1)
        self.hash[key] = v

    def __delitem__(self, key, val):
        del(self.hash[key])

    def __iter__(self, fn=None):
        k = self.hash.first()
        while k != None:
            key = k[0]
            val = pickle.loads(k[1])
            if key not in self.iterskip:
                if fn:
                    yield fn((key, val))
                else:
                    yield (key, val)
            try:
                k = self.hash.next()
            except KeyError:
                break

    def __contains__(self, name):
        return self.has_key(name)

    def __getattr__(self, name):
        # Pass the buck
        return getattr(self.hash, name)

    def get(self, key, dfl=None):
        if self.has_key(key):
            return self[key]
        else:
            return dfl

    def iteritems(self):
        return self.__iter__()

    def iterkeys(self):
        return self.__iter__(lambda k: k[0])

    def itervalues(self):
        return self.__iter__(lambda k: k[1])

    
class PersistentGrahamBayes(classifier.GrahamBayes):
    """A persistent GrahamBayes classifier

    This is just like classifier.GrahamBayes, except that the dictionary
    is a database.  You take less disk this way, I think, and you can
    pretend it's persistent.  It's much slower training, but much faster
    checking, and takes less memory all around.

    On destruction, an instantiation of this class will write it's state
    to a special key.  When you instantiate a new one, it will attempt
    to read these values out of that key again, so you can pick up where
    you left off.

    """

    # XXX: Would it be even faster to remember (in a list) which keys
    # had been modified, and only recalculate those keys?  No sense in
    # going over the entire word database if only 100 words are
    # affected.

    # XXX: Another idea: cache stuff in memory.  But by then maybe we
    # should just use ZODB.

    def __init__(self, dbname):
        classifier.GrahamBayes.__init__(self)
        self.statekey = "saved state"
        self.wordinfo = DBDict(dbname, (self.statekey,))

        self.restore_state()

    def __del__(self):
        #super.__del__(self)
        self.save_state()

    def save_state(self):
        self.wordinfo[self.statekey] = (self.nham, self.nspam)

    def restore_state(self):
        if self.wordinfo.has_key(self.statekey):
            self.nham, self.nspam = self.wordinfo[self.statekey]


class DirOfTxtFileMailbox:

    """Mailbox directory consisting of .txt files."""

    def __init__(self, dirname, factory):
        self.names = glob.glob(os.path.join(dirname, "*.txt"))
        self.factory = factory

    def __iter__(self):
        for name in self.names:
            try:
                f = open(name)
            except IOError:
                continue
            yield self.factory(f)
            f.close()


def train(bayes, msgs, is_spam):
    """Train bayes with a message"""
    def _factory(fp):
        try:
            return email.message_from_file(fp)
        except email.Errors.MessageParseError:
            return ''

    if os.path.isdir(msgs):
        # XXX This is bogus: use an MHMailbox if the pathname contains /Mail/
        # XXX Should really use '+foo' MH folder styles.  Later.
        if msgs.find("/Mail/") >= 0:
            mbox = mailbox.MHMailbox(msgs, _factory)
        else:
            mbox = DirOfTxtFileMailbox(msgs, _factory)
    else:
        fp = open(msgs)
        mbox = mailbox.PortableUnixMailbox(fp, _factory)

    i = 0
    for msg in mbox:
        i += 1
        # XXX: Is the \r a Unixism?  I seem to recall it working in DOS
        # back in the day.  Maybe it's a line-printer-ism ;)
        sys.stdout.write("\r%6d" % i)
        sys.stdout.flush()
        bayes.learn(tokenize(str(msg)), is_spam, False)
    print

def filter(bayes, input, output):
    """Filter (judge) a message"""
    msg = email.message_from_file(input)
    prob, clues = bayes.spamprob(tokenize(str(msg)), True)
    if prob < 0.9:
        disp = "No"
    else:
        disp = "Yes"
    disp += "; %.2f" % prob
    disp += "; " + "; ".join(map(lambda x: "%s: %.2f" % (`x[0]`, x[1]), clues))
    msg.add_header("X-Spam-Disposition", disp)
    output.write(str(msg))

def usage(code, msg=''):
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hdfg:s:p:')
    except getopt.error, msg:
        usage(1, msg)

    if not opts:
        usage(0, "No options given")

    pck = "hammie.db"
    good = spam = None
    do_filter = usedb = False
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-g':
            good = arg
        elif opt == '-s':
            spam = arg
        elif opt == '-p':
            pck = arg
        elif opt == "-d":
            usedb = True
        elif opt == "-f":
            do_filter = True
    if args:
        usage(1)

    save = False

    if usedb:
        bayes = PersistentGrahamBayes(pck)
    else:
        bayes = None
        try:
            fp = open(pck, 'rb')
        except IOError, e:
            if e.errno <> errno.ENOENT: raise
        else:
            bayes = pickle.load(fp)
            fp.close()
        if bayes is None:
            bayes = classifier.GrahamBayes()

    if good:
        print "Training ham:"
        train(bayes, good, False)
        save = True
    if spam:
        print "Training spam:"
        train(bayes, spam, True)
        save = True

    if save:
        bayes.update_probabilities()
        if not usedb and pck:
            fp = open(pck, 'wb')
            pickle.dump(bayes, fp, 1)
            fp.close()

    if do_filter:
        filter(bayes, sys.stdin, sys.stdout)

if __name__ == "__main__":
    main()
