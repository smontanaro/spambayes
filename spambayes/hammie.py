#! /usr/bin/env python

# A driver for the classifier module and Tim's tokenizer that you can
# call from procmail.

"""Usage: %(program)s [options]

Where:
    -h
        show usage and exit
    -g PATH
        mbox or directory of known good messages (non-spam) to train on.
        Can be specified more than once.
    -s PATH
        mbox or directory of known spam messages to train on.
        Can be specified more than once.
    -u PATH
        mbox of unknown messages.  A ham/spam decision is reported for each.
        Can be specified more than once.
    -p FILE
        use file as the persistent store.  loads data from this file if it
        exists, and saves data to this file at the end.  Default: %(DEFAULTDB)s
    -d
        use the DBM store instead of cPickle.  The file is larger and
        creating it is slower, but checking against it is much faster,
        especially for large word databases.
    -f
        run as a filter: read a single message from stdin, add an
        %(DISPHEADER)s header, and write it to stdout.
"""

from __future__ import generators

import sys
import os
import getopt
import mailbox
import glob
import email
import errno
import anydbm
import cPickle as pickle

import mboxutils
import classifier
from Options import options

program = sys.argv[0] # For usage(); referenced by docstring above

# Name of the header to add in filter mode
DISPHEADER = "X-Hammie-Disposition"

# Default database name
DEFAULTDB = "hammie.db"

# Probability at which a message is considered spam
SPAM_THRESHOLD = options.spam_cutoff

# Tim's tokenizer kicks far more booty than anything I would have
# written.  Score one for analysis ;)
from tokenizer import tokenize

class DBDict:

    """Database Dictionary.

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
            val = self.__getitem__(key)
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


class PersistentBayes(classifier.Bayes):

    """A persistent Bayes classifier.

    This is just like classifier.Bayes, except that the dictionary is a
    database.  You take less disk this way and you can pretend it's
    persistent.  The tradeoffs vs. a pickle are: 1. it's slower
    training, but faster checking, and 2. it needs less memory to run,
    but takes more space on the hard drive.

    On destruction, an instantiation of this class will write its state
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
        classifier.Bayes.__init__(self)
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


class Hammie:

    """A spambayes mail filter"""

    def __init__(self, bayes):
        self.bayes = bayes

    def _scoremsg(self, msg, evidence=False):
        """Score a Message.

        msg can be a string, a file object, or a Message object.

        Returns the probability the message is spam.  If evidence is
        true, returns a tuple: (probability, clues), where clues is a
        list of the words which contributed to the score.

        """

        return self.bayes.spamprob(tokenize(msg), evidence)

    def formatclues(self, clues, sep="; "):
        """Format the clues into something readable."""

        return sep.join(["%r: %.2f" % (word, prob) for word, prob in clues])

    def score(self, msg, evidence=False):
        """Score (judge) a message.

        msg can be a string, a file object, or a Message object.

        Returns the probability the message is spam.  If evidence is
        true, returns a tuple: (probability, clues), where clues is a
        list of the words which contributed to the score.

        """

        try:
            return self._scoremsg(msg, evidence)
        except:
            print msg
            import traceback
            traceback.print_exc()

    def filter(self, msg, header=DISPHEADER, cutoff=SPAM_THRESHOLD):
        """Score (judge) a message and add a disposition header.

        msg can be a string, a file object, or a Message object.

        Optionally, set header to the name of the header to add, and/or
        cutoff to the probability value which must be met or exceeded
        for a message to get a 'Yes' disposition.

        Returns the same message with a new disposition header.

        """

        if hasattr(msg, "readlines"):
            msg = email.message_from_file(msg)
        elif not hasattr(msg, "add_header"):
            msg = email.message_from_string(msg)
        prob, clues = self._scoremsg(msg, True)
        if prob < cutoff:
            disp = "No"
        else:
            disp = "Yes"
        disp += "; %.2f" % prob
        disp += "; " + self.formatclues(clues)
        msg.add_header(header, disp)
        return msg.as_string(unixfrom=(msg.get_unixfrom() is not None))

    def train(self, msg, is_spam):
        """Train bayes with a message.

        msg can be a string, a file object, or a Message object.

        is_spam should be 1 if the message is spam, 0 if not.

        Probabilities are not updated after this call is made; to do
        that, call update_probabilities().

        """

        self.bayes.learn(tokenize(msg), is_spam, False)

    def train_ham(self, msg):
        """Train bayes with ham.

        msg can be a string, a file object, or a Message object.

        Probabilities are not updated after this call is made; to do
        that, call update_probabilities().

        """

        self.train(msg, False)

    def train_spam(self, msg):
        """Train bayes with spam.

        msg can be a string, a file object, or a Message object.

        Probabilities are not updated after this call is made; to do
        that, call update_probabilities().

        """

        self.train(msg, True)

    def update_probabilities(self):
        """Update probability values.

        You would want to call this after a training session.  It's
        pretty slow, so if you have a lot of messages to train, wait
        until you're all done before calling this.

        """

        self.bayes.update_probabilities()


def train(hammie, msgs, is_spam):
    """Train bayes with all messages from a mailbox."""
    mbox = mboxutils.getmbox(msgs)
    i = 0
    for msg in mbox:
        i += 1
        # XXX: Is the \r a Unixism?  I seem to recall it working in DOS
        # back in the day.  Maybe it's a line-printer-ism ;)
        sys.stdout.write("\r%6d" % i)
        sys.stdout.flush()
        hammie.train(msg, is_spam)
    print

def score(hammie, msgs):
    """Score (judge) all messages from a mailbox."""
    # XXX The reporting needs work!
    mbox = mboxutils.getmbox(msgs)
    i = 0
    spams = hams = 0
    for msg in mbox:
        i += 1
        prob, clues = hammie.score(msg, True)
        isspam = prob >= SPAM_THRESHOLD
        if hasattr(msg, '_mh_msgno'):
            msgno = msg._mh_msgno
        else:
            msgno = i
        if isspam:
            spams += 1
            print "%6s %4.2f %1s" % (msgno, prob, isspam and "S" or "."),
            print hammie.formatclues(clues)
        else:
            hams += 1
    print "Total %d spam, %d ham" % (spams, hams)

def createbayes(pck=DEFAULTDB, usedb=False):
    """Create a Bayes instance for the given pickle (which
    doesn't have to exist).  Create a PersistentBayes if
    usedb is True."""
    if usedb:
        bayes = PersistentBayes(pck)
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
            bayes = classifier.Bayes()
    return bayes

def usage(code, msg=''):
    """Print usage message and sys.exit(code)."""
    if msg:
        print >> sys.stderr, msg
        print >> sys.stderr
    print >> sys.stderr, __doc__ % globals()
    sys.exit(code)

def main():
    """Main program; parse options and go."""
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'hdfg:s:p:u:')
    except getopt.error, msg:
        usage(2, msg)

    if not opts:
        usage(2, "No options given")

    pck = DEFAULTDB
    good = []
    spam = []
    unknown = []
    do_filter = usedb = False
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-g':
            good.append(arg)
        elif opt == '-s':
            spam.append(arg)
        elif opt == '-p':
            pck = arg
        elif opt == "-d":
            usedb = True
        elif opt == "-f":
            do_filter = True
        elif opt == '-u':
            unknown.append(arg)
    if args:
        usage(2, "Positional arguments not allowed")

    save = False

    bayes = createbayes(pck, usedb)
    h = Hammie(bayes)

    for g in good:
        print "Training ham (%s):" % g
        train(h, g, False)
        save = True

    for s in spam:
        print "Training spam (%s):" % s
        train(h, s, True)
        save = True

    if save:
        h.update_probabilities()
        if not usedb and pck:
            fp = open(pck, 'wb')
            pickle.dump(bayes, fp, 1)
            fp.close()

    if do_filter:
        msg = sys.stdin.read()
        filtered = h.filter(msg)
        sys.stdout.write(filtered)

    if unknown:
        for u in unknown:
            if len(unknown) > 1:
                print "Scoring", u
            score(h, u)

if __name__ == "__main__":
    main()
