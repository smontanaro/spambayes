#! /usr/bin/env python

# A driver for the classifier module and Tim's tokenizer that you can
# call from procmail.

"""Usage: %(program)s [options]

Where:
    -h
        show usage and exit
    -g PATH
        mbox or directory of known good messages (non-spam) to train on.
        Can be specified more than once, or use - for stdin.
    -s PATH
        mbox or directory of known spam messages to train on.
        Can be specified more than once, or use - for stdin.
    -u PATH
        mbox of unknown messages.  A ham/spam decision is reported for each.
        Can be specified more than once.
    -r
        reverse the meaning of the check (report ham instead of spam).
        Only meaningful with the -u option.
    -p FILE
        use file as the persistent store.  loads data from this file if it
        exists, and saves data to this file at the end.
        Default: %(DEFAULTDB)s
    -d
        use the DBM store instead of cPickle.  The file is larger and
        creating it is slower, but checking against it is much faster,
        especially for large word databases. Default: %(USEDB)s
    -D
        the reverse of -d: use the cPickle instead of DBM
    -f
        run as a filter: read a single message from stdin, add an
        %(DISPHEADER)s header, and write it to stdout.  If you want to
        run from procmail, this is your option.
"""

from __future__ import generators

import sys
import os
import types
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

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0


program = sys.argv[0] # For usage(); referenced by docstring above

# Name of the header to add in filter mode
DISPHEADER = options.hammie_header_name
DEBUGHEADER = options.hammie_debug_header_name
DODEBUG = options.hammie_debug_header

# Default database name
DEFAULTDB = options.persistent_storage_file

# Probability at which a message is considered spam
SPAM_THRESHOLD = options.spam_cutoff
HAM_THRESHOLD = options.ham_cutoff

# Probability limit for a clue to be added to the DISPHEADER
SHOWCLUE = options.clue_mailheader_cutoff

# Use a database? If False, use a pickle
USEDB = options.persistent_use_database

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

    def __init__(self, dbname, mode, iterskip=()):
        self.hash = anydbm.open(dbname, mode)
        self.iterskip = iterskip

    def __getitem__(self, key):
        v = self.hash[key]
        if v[0] == 'W':
            val = pickle.loads(v[1:])
            # We could be sneaky, like pickle.Unpickler.load_inst,
            # but I think that's overly confusing.
            obj = classifier.WordInfo(0)
            obj.__setstate__(val)
            return obj
        else:
            return pickle.loads(v)

    def __setitem__(self, key, val):
        if isinstance(val, classifier.WordInfo):
            val = val.__getstate__()
            v = 'W' + pickle.dumps(val, 1)
        else:
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

    def __init__(self, dbname, mode):
        classifier.Bayes.__init__(self)
        self.statekey = "saved state"
        self.wordinfo = DBDict(dbname, mode, (self.statekey,))
        self.dbmode = mode

        self.restore_state()

    def __del__(self):
        #super.__del__(self)
        self.save_state()

    def save_state(self):
        if self.dbmode != 'r':
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

        return sep.join(["%r: %.2f" % (word, prob)
                         for word, prob in clues
                         if (word[0] == '*' or
                             prob <= SHOWCLUE or prob >= 1.0 - SHOWCLUE)])

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

    def filter(self, msg, header=DISPHEADER, spam_cutoff=SPAM_THRESHOLD,
               ham_cutoff=HAM_THRESHOLD, debugheader=DEBUGHEADER,
               debug=DODEBUG):
        """Score (judge) a message and add a disposition header.

        msg can be a string, a file object, or a Message object.

        Optionally, set header to the name of the header to add, and/or
        spam_cutoff/ham_cutoff to the probability values which must be met
        or exceeded for a message to get a 'Spam' or 'Ham' classification.

        An extra debugging header can be added if 'debug' is set to True.
        The name of the debugging header is given as 'debugheader'.

        All defaults for optional parameters come from the Options file.

        Returns the same message with a new disposition header.

        """

        msg = mboxutils.get_message(msg)
        prob, clues = self._scoremsg(msg, True)
        if prob < ham_cutoff:
            disp = options.header_ham_string
        elif prob > spam_cutoff:
            disp = options.header_spam_string
        else:
            disp = options.header_unsure_string
        disp += ("; %."+str(options.header_score_digits)+"f") % prob
        if options.header_score_logarithm:
            if prob<=0.005 and prob>0.0:
                import math
                x=-math.log10(prob)
                disp += " (%d)"%x
            if prob>=0.995 and prob<1.0:
                import math
                x=-math.log10(1.0-prob)
                disp += " (%d)"%x
        msg.add_header(header, disp)
        if debug:
            disp = self.formatclues(clues)
            msg.add_header(debugheader, disp)
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

def score(hammie, msgs, reverse=0):
    """Score (judge) all messages from a mailbox."""
    # XXX The reporting needs work!
    mbox = mboxutils.getmbox(msgs)
    i = 0
    spams = hams = 0
    for msg in mbox:
        i += 1
        prob, clues = hammie.score(msg, True)
        if hasattr(msg, '_mh_msgno'):
            msgno = msg._mh_msgno
        else:
            msgno = i
        isspam = (prob >= SPAM_THRESHOLD)
        if isspam:
            spams += 1
            if not reverse:
                print "%6s %4.2f %1s" % (msgno, prob, isspam and "S" or "."),
                print hammie.formatclues(clues)
        else:
            hams += 1
            if reverse:
                print "%6s %4.2f %1s" % (msgno, prob, isspam and "S" or "."),
                print hammie.formatclues(clues)
    return (spams, hams)

def createbayes(pck=DEFAULTDB, usedb=False, mode='r'):
    """Create a Bayes instance for the given pickle (which
    doesn't have to exist).  Create a PersistentBayes if
    usedb is True."""
    if usedb:
        bayes = PersistentBayes(pck, mode)
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
        opts, args = getopt.getopt(sys.argv[1:], 'hdDfg:s:p:u:r')
    except getopt.error, msg:
        usage(2, msg)

    if not opts:
        usage(2, "No options given")

    pck = DEFAULTDB
    good = []
    spam = []
    unknown = []
    reverse = 0
    do_filter = False
    usedb = USEDB
    mode = 'r'
    for opt, arg in opts:
        if opt == '-h':
            usage(0)
        elif opt == '-g':
            good.append(arg)
            mode = 'c'
        elif opt == '-s':
            spam.append(arg)
            mode = 'c'
        elif opt == '-p':
            pck = arg
        elif opt == "-d":
            usedb = True
        elif opt == "-D":
            usedb = False
        elif opt == "-f":
            do_filter = True
        elif opt == '-u':
            unknown.append(arg)
        elif opt == '-r':
            reverse = 1
    if args:
        usage(2, "Positional arguments not allowed")

    save = False

    bayes = createbayes(pck, usedb, mode)
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
        (spams, hams) = (0, 0)
        for u in unknown:
            if len(unknown) > 1:
                print "Scoring", u
            s, g = score(h, u, reverse)
            spams += s
            hams += g
        print "Total %d spam, %d ham" % (spams, hams)


if __name__ == "__main__":
    main()
