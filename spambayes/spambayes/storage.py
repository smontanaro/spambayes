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
        # that pickle does its job

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

        # XXX: why not self.__setstate__(tempbayes.__getstate__())?
        if tempbayes:
            self.wordinfo = tempbayes.wordinfo
            self.nham = tempbayes.nham
            self.nspam = tempbayes.nspam

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

    def store(self):
        '''Place state into persistent store'''

        if options.verbose:
            print 'Persisting',self.db_name,'state in database'

        # Must use .keys() since we modify the dict in the loop
        for key in self.wordinfo.keys():
            val = self.wordinfo[key]
            if val is None:
                del self.wordinfo[key]
                try:
                    del self.db[key]
                except KeyError:
                    pass
            else:
                self.db[key] = val.__getstate__()
        self.db[self.statekey] = (classifier.PICKLE_VERSION,
                                  self.nspam, self.nham)
        self.db.sync()

    def _wordinfoget(self, word):
        # Note an explicit None in the dict means the word
        # has previously been deleted, but the DB has not been saved,
        # so therefore should not be re-fecthed.
        try:
            return self.wordinfo[word]
        except KeyError:
            ret = None
            r = self.db.get(word)
            if r:
                ret = self.WordInfoClass()
                ret.__setstate__(r)
                self.wordinfo[word] = ret
            return ret

    # _wordinfoset is the same

    def _wordinfodel(self, word):
        self.wordinfo[word] = None


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
