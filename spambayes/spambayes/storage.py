#! /usr/bin/env python

'''storage.py - Spambayes database management framework.

Classes:
    PickledClassifier - Classifier that uses a pickle db
    DBDictClassifier - Classifier that uses a shelve db
    Trainer - Classifier training observer
    SpamTrainer - Trainer for spam
    HamTrainer - Trainer for ham

Abstract:
    *Classifier are subclasses of Classifier (classifier.Classifier)
    that add automatic state store/restore function to the Classifier class.

    PickledClassifier is a Classifier class that uses a cPickle
    datastore.  This database is relatively small, but slower than other
    databases.

    DBDictClassifier is a Classifier class that uses a database
    store.

    Trainer is concrete class that observes a Corpus and trains a
    Classifier object based upon movement of messages between corpora  When
    an add message notification is received, the trainer trains the
    database with the message, as spam or ham as appropriate given the
    type of trainer (spam or ham).  When a remove message notification
    is received, the trainer untrains the database as appropriate.

    SpamTrainer and HamTrainer are convenience subclasses of Trainer, that
    initialize as the appropriate type of Trainer

To Do:
    o ZODBClassifier
    o Would Trainer.trainall really want to train with the whole corpus,
        or just a random subset?
    o Suggestions?

    '''

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Neale Pickett <neale@woozle.org>, \
Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "All the spambayes contributors."

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    def bool(val):
        return not not val

from spambayes import classifier
from spambayes.Options import options
import cPickle as pickle
import errno
import shelve
from spambayes import dbmstorage

# Make shelve use binary pickles by default.
oldShelvePickler = shelve.Pickler
def binaryDefaultPickler(f, binary=1):
    return oldShelvePickler(f, binary)
shelve.Pickler = binaryDefaultPickler

PICKLE_TYPE = 1
NO_UPDATEPROBS = False   # Probabilities will not be autoupdated with training
UPDATEPROBS = True       # Probabilities will be autoupdated with training

class PickledClassifier(classifier.Classifier):
    '''Classifier object persisted in a pickle'''

    def __init__(self, db_name):
        classifier.Classifier.__init__(self)
        self.db_name = db_name
        self.load()

    def load(self):
        '''Load this instance from the pickle.'''
        # This is a bit strange, because the loading process
        # creates a temporary instance of PickledClassifier, from which
        # this object's state is copied.  This is a nuance of the way
        # that pickle does its job.
        # Tim sez:  that's because this is an unusual way to use pickle.
        # Note that nothing non-trivial is actually copied, though:
        # assignment merely copies a pointer.  The actual wordinfo etc
        # objects are shared between tempbayes and self, and the tiny
        # tempbayes object is reclaimed when load() returns.

        if options.verbose:
            print 'Loading state from',self.db_name,'pickle'

        tempbayes = None
        try:
            fp = open(self.db_name, 'rb')
        except IOError, e:
            if e.errno != errno.ENOENT: raise
        else:
            tempbayes = pickle.load(fp)
            fp.close()

        if tempbayes:
            # Copy state from tempbayes.  The use of our base-class
            # __setstate__ is forced, in case self is of a subclass of
            # PickledClassifier that overrides __setstate__.
            classifier.Classifier.__setstate__(self,
                                               tempbayes.__getstate__())
            if options.verbose:
                print '%s is an existing pickle, with %d ham and %d spam' \
                      % (self.db_name, self.nham, self.nspam)
        else:
            # new pickle
            if options.verbose:
                print self.db_name,'is a new pickle'
            self.wordinfo = {}
            self.nham = 0
            self.nspam = 0

    def store(self):
        '''Store self as a pickle'''

        if options.verbose:
            print 'Persisting',self.db_name,'as a pickle'

        fp = open(self.db_name, 'wb')
        pickle.dump(self, fp, PICKLE_TYPE)
        fp.close()

# Values for our changed words map
WORD_DELETED = "D"
WORD_CHANGED = "C"

class DBDictClassifier(classifier.Classifier):
    '''Classifier object persisted in a caching database'''

    def __init__(self, db_name, mode='c'):
        '''Constructor(database name)'''

        classifier.Classifier.__init__(self)
        self.statekey = "saved state"
        self.mode = mode
        self.db_name = db_name
        self.load()

    def load(self):
        '''Load state from database'''

        if options.verbose:
            print 'Loading state from',self.db_name,'database'

        self.dbm = dbmstorage.open(self.db_name, self.mode)
        self.db = shelve.Shelf(self.dbm)

        if self.db.has_key(self.statekey):
            t = self.db[self.statekey]
            if t[0] != classifier.PICKLE_VERSION:
                raise ValueError("Can't unpickle -- version %s unknown" % t[0])
            (self.nspam, self.nham) = t[1:]

            if options.verbose:
                print '%s is an existing database, with %d spam and %d ham' \
                      % (self.db_name, self.nspam, self.nham)
        else:
            # new database
            if options.verbose:
                print self.db_name,'is a new database'
            self.nspam = 0
            self.nham = 0
        self.wordinfo = {}
        self.changed_words = {} # value may be one of the WORD_ constants

    def store(self):
        '''Place state into persistent store'''

        if options.verbose:
            print 'Persisting',self.db_name,'state in database'

        # Iterate over our changed word list.
        # This is *not* thread-safe - another thread changing our
        # changed_words could mess us up a little.  Possibly a little
        # lock while we copy and reset self.changed_words would be appropriate.
        # For now, just do it the naive way.
        for key, flag in self.changed_words.items():
            if flag is WORD_CHANGED:
                val = self.wordinfo[key]
                self.db[key] = val.__getstate__()
            elif flag is WORD_DELETED:
                assert word not in self.wordinfo, \
                       "Should not have a wordinfo for words flagged for delete"
                # Word may be deleted before it was ever written.
                # hrmph - working out what exceptions would be reasonable is
                # a PITA (but anydbm.errors may be useful) - but for now,
                # just check the key first.
                if self.db.has_key(key):
                    del self.db[key]
            else:
                raise RuntimeError, "Unknown flag value"

        # Reset the changed word list.
        self.changed_words = {}
        # Update the global state, then do the actual save.
        self.db[self.statekey] = (classifier.PICKLE_VERSION,
                                  self.nspam, self.nham)
        self.db.sync()

    def _wordinfoget(self, word):
        try:
            return self.wordinfo[word]
        except KeyError:
            ret = None
            if self.changed_words.get(word) is not WORD_DELETED:
                r = self.db.get(word)
                if r:
                    ret = self.WordInfoClass()
                    ret.__setstate__(r)
                    self.wordinfo[word] = ret
            return ret

    def _wordinfoset(self, word, record):
        # "Singleton" words (i.e. words that only have a single instance)
        # take up more than 1/2 of the database, but are rarely used
        # so we don't put them into the wordinfo cache, but write them
        # directly to the database
        # If the word occurs again, then it will be brought back in and
        # never be a singleton again.
        # This seems to reduce the memory footprint of the DBDictClassifier by
        # as much as 60%!!!  This also has the effect of reducing the time it
        # takes to store the database
        if record.spamcount + record.hamcount <= 1:
            self.db[word] = record.__getstate__()
            # Remove this word from the changed list (not that it should be
            # there, but strange things can happen :)
            try:
                del self.changed_words[word]
            except KeyError:
                pass
        else:
            self.wordinfo[word] = record
            self.changed_words[word] = WORD_CHANGED

    def _wordinfodel(self, word):
        del self.wordinfo[word]
        self.changed_words[word] = WORD_DELETED

class Trainer:
    '''Associates a Classifier object and one or more Corpora, \
    is an observer of the corpora'''

    def __init__(self, bayes, is_spam, updateprobs=NO_UPDATEPROBS):
        '''Constructor(Classifier, is_spam(True|False), updprobs(True|False)'''

        self.bayes = bayes
        self.is_spam = is_spam
        self.updateprobs = updateprobs

    def onAddMessage(self, message):
        '''A message is being added to an observed corpus.'''

        self.train(message)

    def train(self, message):
        '''Train the database with the message'''

        if options.verbose:
            print 'training with',message.key()

        self.bayes.learn(message.tokenize(), self.is_spam)
#                         self.updateprobs)

    def onRemoveMessage(self, message):
        '''A message is being removed from an observed corpus.'''

        self.untrain(message)

    def untrain(self, message):
        '''Untrain the database with the message'''

        if options.verbose:
            print 'untraining with',message.key()

        self.bayes.unlearn(message.tokenize(), self.is_spam)
#                           self.updateprobs)
        # can raise ValueError if database is fouled.  If this is the case,
        # then retraining is the only recovery option.

    def trainAll(self, corpus):
        '''Train all the messages in the corpus'''

        for msg in corpus:
            self.train(msg)

    def untrainAll(self, corpus):
        '''Untrain all the messages in the corpus'''

        for msg in corpus:
            self.untrain(msg)


class SpamTrainer(Trainer):
    '''Trainer for spam'''

    def __init__(self, bayes, updateprobs=NO_UPDATEPROBS):
        '''Constructor'''

        Trainer.__init__(self, bayes, True, updateprobs)


class HamTrainer(Trainer):
    '''Trainer for ham'''

    def __init__(self, bayes, updateprobs=NO_UPDATEPROBS):
        '''Constructor'''

        Trainer.__init__(self, bayes, False, updateprobs)


if __name__ == '__main__':
    import sys
    print >> sys.stderr, __doc__
