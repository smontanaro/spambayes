#! /usr/bin/env python

'''Bayes.py - Spambayes database management framework.

Classes:
    PersistentBayes - subclass of Bayes, adds auto persistence
    PickledBayes - PersistentBayes that uses a pickle db
    DBDictBayes - PersistentBayes that uses a (hammie.) DB_Dict db
    Trainer - Bayes training observer
    SpamTrainer - Trainer for spam
    HamTrainer - Trainer for ham

Abstract:
    PersistentBayes is an abstract subclass of Bayes (classifier.Bayes)
    that adds automatic state store/restore function to the Bayes class.
    It also adds a convenience method, which should probably
    more properly be defined in Bayes: classify, which returns
    'spam'|'ham'|'unsure' for a message based on the spamprob against
    the ham_cutoff and spam_cutoff specified in Options.
    
    PickledBayes is a concrete PersistentBayes class that uses a cPickle
    datastore.  This database is relatively small, but slower than other
    databases.

    DBDictBayes is a concrete PersistentBayes class that uses a DB_Dict
    datastore.  DB_Dict is currently definied in hammie.py, and wraps
    an anydbm with some very convenient dictionary functionality, such as
    the ability to skip particular keys or key patterns during iteration.

    Trainer is concrete class that observes a Corpus and trains a
    Bayes object based upon movement of messages between corpora  When
    an add message notification is received, the trainer trains the
    database with the message, as spam or ham as appropriate given the
    type of trainer (spam or ham).  When a remove message notification
    is received, the trainer untrains the database as appropriate.

    SpamTrainer and HamTrainer are convenience subclasses of Trainer, that
    initialize as the appropriate type of Trainer

To Do:
    o ZODBBayes
    o Would Trainer.trainall really want to train with the whole corpus,
      or just a random subset?
    o Corpus.Verbose is a bit of a strange thing to have.  Verbose should be
      in the global namespace, but how do you get it there?
    o Suggestions?

    '''

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "Richie Hindle, Tim Peters, Neil Gunton, \
all the spambayes contributors."

import Corpus
from classifier import Bayes
from Options import options
from hammie import DBDict     # hammie only for DBDict, which should
                              # probably really be somewhere else
import cPickle as pickle
import errno

PICKLE_TYPE = 1
NO_UPDATEPROBS = False   # Probabilities will not be autoupdated with training
UPDATEPROBS = True       # Probabilities will be autoupdated with training

class PersistentBayes(Bayes):
    '''Persistent Bayes database object'''

    def __init__(self, db_name):
        '''Constructor(database name)'''

        self.db_name = db_name
        self.load()

    def load(self):
        '''Restore state from a persistent store'''

        raise NotImplementedError

    def store(self):
        '''Persist state into a persistent store'''

        raise NotImplementedError

    def classify(self, message):
        '''Returns the classification of a Message {'spam'|'ham'|'unsure'}'''

        prob = self.spamprob(message.tokenize())

        message.setSpamprob(prob)   # don't like this

        if prob < options.ham_cutoff:
            type = 'ham'
        elif prob > options.spam_cutoff:
            type = 'spam'
        else:
            type = 'unsure'

        return type


class PickledBayes(PersistentBayes):
    '''Bayes object persisted in a pickle'''

    def load(self):
        '''Load this instance from the pickle.'''
        # This is a bit strange, because the loading process
        # creates a temporary instance of PickledBayes, from which
        # this object's state is copied.  This is a nuance of the way
        # that pickle does its job

        if Corpus.Verbose:
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
            self.wordinfo = tempbayes.wordinfo
            self.nham = tempbayes.nham
            self.nspam = tempbayes.nspam
            
            if Corpus.Verbose:
                print '%s is an existing pickle, with %d ham and %d spam' \
                      % (self.db_name, self.nham, self.nspam)
        else:
            # new pickle
            if Corpus.Verbose:
                print self.db_name,'is a new pickle'
            self.wordinfo = {}
            self.nham = 0
            self.nspam = 0

    def store(self):
        '''Store self as a pickle'''

        if Corpus.Verbose:
            print 'Persisting',self.db_name,'as a pickle'

        fp = open(self.db_name, 'wb')
        pickle.dump(self, fp, PICKLE_TYPE)
        fp.close()

    def __getstate__(self):
        '''State requested by pickler'''

        return PICKLE_TYPE, self.wordinfo, self.nspam, self.nham

    def __setstate__(self, t):
        '''State provided by pickler'''
        # This can be confusing, because self in this method
        # is not the same instance as self in the load() method

        if t[0] != PICKLE_TYPE:
            raise ValueError("Can't unpickle -- version %s unknown" % t[0])

        self.wordinfo, self.nspam, self.nham = t[1:]
        

class DBDictBayes(PersistentBayes):
    '''Bayes object persisted in a hammie.DB_Dict'''

    def __init__(self, db_name):
        '''Constructor(database name)'''

        self.db_name = db_name
        self.statekey = "saved state"
        self.wordinfo = DBDict(db_name, (self.statekey,), 'c')  # r/rw?

        self.load()

    def load(self):
        '''Load state from DB_Dict'''

        if Corpus.Verbose:
            print 'Loading state from',self.db_name,'DB_Dict'

        if self.wordinfo.has_key(self.statekey):
            self.nham, self.nspam = self.wordinfo[self.statekey]
            
            if Corpus.Verbose:
                print '%s is an existing DBDict, with %d ham and %d spam' \
                      % (self.db_name, self.nham, self.nspam)
        else:
            # new dbdict
            if Corpus.Verbose:
                print self.db_name,'is a new DBDict'
            self.nham = 0
            self.nspam = 0

    def store(self):
        '''Place state into persistent store'''

        if Corpus.Verbose:
            print 'Persisting',self.db_name,'state in DBDict'

        self.wordinfo[self.statekey] = (self.nham, self.nspam)


class Trainer:
    '''Associates a Bayes object and one or more Corpora, \
    is an observer of the corpora'''

    def __init__(self, bayes, trainertype, updateprobs=NO_UPDATEPROBS):
        '''Constructor(Bayes, \
                       Corpus.SPAM|Corpus.HAM), updprobs(True|False)'''

        self.bayes = bayes
        self.trainertype = trainertype
        self.updateprobs = updateprobs

    def onAddMessage(self, message):
        '''A message is being added to an observed corpus.'''

        self.train(message)

    def train(self, message):
        '''Train the database with the message'''

        if Corpus.Verbose:
            print 'training with',message.key()

        self.bayes.learn(message.tokenize(), \
                         self.trainertype, \
                         self.updateprobs)

    def onRemoveMessage(self, message):
        '''A message is being removed from an observed corpus.'''

        self.untrain(message)

    def untrain(self, message):
        '''Untrain the database with the message'''

        if Corpus.Verbose:
            print 'untraining with',message.key()

        self.bayes.unlearn(message.tokenize(), \
                           self.trainertype, \
                           self.updateprobs)
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

        Trainer.__init__(self, bayes, Corpus.SPAM, updateprobs)


class HamTrainer(Trainer):
    '''Trainer for ham'''

    def __init__(self, bayes, updateprobs=NO_UPDATEPROBS):
        '''Constructor'''

        Trainer.__init__(self, bayes, Corpus.HAM, updateprobs)


if __name__ == '__main__':
    print >>sys.stderr, __doc__