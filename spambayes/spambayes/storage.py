#! /usr/bin/env python

'''storage.py - Spambayes database management framework.

Classes:
    PickledClassifier - Classifier that uses a pickle db
    DBDictClassifier - Classifier that uses a shelve db
    PGClassifier - Classifier that uses postgres
    mySQLClassifier - Classifier that uses mySQL
    Trainer - Classifier training observer
    SpamTrainer - Trainer for spam
    HamTrainer - Trainer for ham

Abstract:
    *Classifier are subclasses of Classifier (classifier.Classifier)
    that add automatic state store/restore function to the Classifier class.
    All SQL based classifiers are subclasses of SQLClassifier, which is a
    subclass of Classifier.

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

### Note to authors - please direct all prints to sys.stderr.  In some
### situations prints to sys.stdout will garble the message (e.g., in
### hammiefilter).

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

import sys, types
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

        if options["globals", "verbose"]:
            print >> sys.stderr, 'Loading state from',self.db_name,'pickle'

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
            if options["globals", "verbose"]:
                print >> sys.stderr, ('%s is an existing pickle,'
                                      ' with %d ham and %d spam') \
                      % (self.db_name, self.nham, self.nspam)
        else:
            # new pickle
            if options["globals", "verbose"]:
                print >> sys.stderr, self.db_name,'is a new pickle'
            self.wordinfo = {}
            self.nham = 0
            self.nspam = 0

    def store(self):
        '''Store self as a pickle'''

        if options["globals", "verbose"]:
            print >> sys.stderr, 'Persisting',self.db_name,'as a pickle'

        fp = open(self.db_name, 'wb')
        pickle.dump(self, fp, PICKLE_TYPE)
        fp.close()

    def close(self):
        # we keep no reasources open - nothing to do
        pass

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

    def close(self):
        # Close our underlying database.  Better not assume all databases
        # have close functions!
        def noop(): pass
        getattr(self.db, "close", noop)()
        getattr(self.dbm, "close", noop)()
        # should not be a need to drop the 'dbm' or 'db' attributes.

    def load(self):
        '''Load state from database'''

        if options["globals", "verbose"]:
            print >> sys.stderr, 'Loading state from',self.db_name,'database'

        self.dbm = dbmstorage.open(self.db_name, self.mode)
        self.db = shelve.Shelf(self.dbm)

        if self.db.has_key(self.statekey):
            t = self.db[self.statekey]
            if t[0] != classifier.PICKLE_VERSION:
                raise ValueError("Can't unpickle -- version %s unknown" % t[0])
            (self.nspam, self.nham) = t[1:]

            if options["globals", "verbose"]:
                print >> sys.stderr, ('%s is an existing database,'
                                      ' with %d spam and %d ham') \
                      % (self.db_name, self.nspam, self.nham)
        else:
            # new database
            if options["globals", "verbose"]:
                print >> sys.stderr, self.db_name,'is a new database'
            self.nspam = 0
            self.nham = 0
        self.wordinfo = {}
        self.changed_words = {} # value may be one of the WORD_ constants

    def store(self):
        '''Place state into persistent store'''

        if options["globals", "verbose"]:
            print >> sys.stderr, 'Persisting',self.db_name,'state in database'

        # Iterate over our changed word list.
        # This is *not* thread-safe - another thread changing our
        # changed_words could mess us up a little.  Possibly a little
        # lock while we copy and reset self.changed_words would be appropriate.
        # For now, just do it the naive way.
        for key, flag in self.changed_words.iteritems():
            if flag is WORD_CHANGED:
                val = self.wordinfo[key]
                self.db[key] = val.__getstate__()
            elif flag is WORD_DELETED:
                assert key not in self.wordinfo, \
                       "Should not have a wordinfo for words flagged for delete"
                # Word may be deleted before it was ever written.
                try:
                    del self.db[key]
                except KeyError:
                    pass
            else:
                raise RuntimeError, "Unknown flag value"

        # Reset the changed word list.
        self.changed_words = {}
        # Update the global state, then do the actual save.
        self._write_state_key()
        self.db.sync()
        
    def _write_state_key(self):
        self.db[self.statekey] = (classifier.PICKLE_VERSION,
                                  self.nspam, self.nham)

    def _post_training(self):
        """This is called after training on a wordstream.  We ensure that the
        database is in a consistent state at this point by writing the state
        key."""
        self._write_state_key()
    
    def _wordinfoget(self, word):
        if isinstance(word, unicode):
            word = word.encode("utf-8")
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
        if isinstance(word, unicode):
            word = word.encode("utf-8")
        if record.spamcount + record.hamcount <= 1:
            self.db[word] = record.__getstate__()
            try:
                del self.changed_words[word]
            except KeyError:
                # This can happen if, e.g., a new word is trained as ham
                # twice, then untrained once, all before a store().
                pass

            try:
                del self.wordinfo[word]
            except KeyError:
                pass

        else:
            self.wordinfo[word] = record
            self.changed_words[word] = WORD_CHANGED

    def _wordinfodel(self, word):
        if isinstance(word, unicode):
            word = word.encode("utf-8")
        del self.wordinfo[word]
        self.changed_words[word] = WORD_DELETED

    def _wordinfokeys(self):
        wordinfokeys = self.db.keys()
        del wordinfokeys[wordinfokeys.index(self.statekey)]
        return wordinfokeys


class SQLClassifier(classifier.Classifier):
    def __init__(self, db_name):
        '''Constructor(database name)'''

        classifier.Classifier.__init__(self)
        self.statekey = "saved state"
        self.db_name = db_name
        self.load()

    def close(self):
        '''Release all database resources'''
        # As we (presumably) aren't as constrained as we are by file locking,
        # don't force sub-classes to override
        pass

    def load(self):
        '''Load state from the database'''
        raise NotImplementedError, "must be implemented in subclass"

    def store(self):
        '''Save state to the database'''
        self._set_row(self.statekey, self.nspam, self.nham)

    def cursor(self):
        '''Return a new db cursor'''
        raise NotImplementedError, "must be implemented in subclass"

    def fetchall(self, c):
        '''Return all rows as a dict'''
        raise NotImplementedError, "must be implemented in subclass"

    def commit(self, c):
        '''Commit the current transaction - may commit at db or cursor'''
        raise NotImplementedError, "must be implemented in subclass"
        
    def create_bayes(self):
        '''Create a new bayes table'''
        c = self.cursor()
        c.execute(self.table_definition)
        self.commit(c)

    def _get_row(self, word):
        '''Return row matching word'''
        try:
            c = self.cursor()
            c.execute("select * from bayes"
                      "  where word=%s",
                      (word,))
        except Exception, e:
            print >> sys.stderr, "error:", (e, word)
            raise
        rows = self.fetchall(c)

        if rows:
            return rows[0]
        else:
            return {}

    def _set_row(self, word, nspam, nham):
        c = self.cursor()
        if self._has_key(word):
            c.execute("update bayes"
                      "  set nspam=%s,nham=%s"
                      "  where word=%s",
                      (nspam, nham, word))
        else:
            c.execute("insert into bayes"
                      "  (nspam, nham, word)"
                      "  values (%s, %s, %s)",
                      (nspam, nham, word))
        self.commit(c)

    def _delete_row(self, word):
        c = self.cursor()
        c.execute("delete from bayes"
                  "  where word=%s",
                  (word,))
        self.commit(c)

    def _has_key(self, key):
        c = self.cursor()
        c.execute("select word from bayes"
                  "  where word=%s",
                  (key,))
        return len(self.fetchall(c)) > 0

    def _wordinfoget(self, word):
        if isinstance(word, unicode):
            word = word.encode("utf-8")

        row = self._get_row(word)
        if row:
            item = self.WordInfoClass()
            item.__setstate__((row["nspam"], row["nham"]))
            return item
        else:
            return self.WordInfoClass()

    def _wordinfoset(self, word, record):
        if isinstance(word, unicode):
            word = word.encode("utf-8")
        self._set_row(word, record.spamcount, record.hamcount)

    def _wordinfodel(self, word):
        if isinstance(word, unicode):
            word = word.encode("utf-8")
        self._delete_row(word)

    def _wordinfokeys(self):
        c = self.cursor()
        c.execute("select word from bayes")
        rows = self.fetchall(c)
        # There is probably some clever way to do this with map or
        # something, but I don't know what it is.  We want the first
        # element from all the items in 'rows'
        keys = []
        for r in rows:
            keys.append(r[0])
        return keys


class PGClassifier(SQLClassifier):
    '''Classifier object persisted in a Postgres database'''
    def __init__(self, db_name):
        self.table_definition = ("create table bayes ("
                                 "  word bytea not null default '',"
                                 "  nspam integer not null default 0,"
                                 "  nham integer not null default 0,"
                                 "  primary key(word)"
                                 ")")
        SQLClassifier.__init__(self, db_name)

    def cursor(self):
        return self.db.cursor()

    def fetchall(self, c):
        return c.dictfetchall()

    def commit(self, c):
        self.db.commit()

    def load(self):
        '''Load state from database'''

        import psycopg
        
        if options["globals", "verbose"]:
            print >> sys.stderr, 'Loading state from',self.db_name,'database'

        self.db = psycopg.connect(self.db_name)

        c = self.cursor()
        try:
            c.execute("select count(*) from bayes")
        except psycopg.ProgrammingError:
            self.db.rollback()
            self.create_bayes()
        
        if self._has_key(self.statekey):
            row = self._get_row(self.statekey)
            self.nspam = row["nspam"]
            self.nham = row["nham"]
            if options["globals", "verbose"]:
                print >> sys.stderr, ('%s is an existing database,'
                                      ' with %d spam and %d ham') \
                      % (self.db_name, self.nspam, self.nham)
        else:
            # new database
            if options["globals", "verbose"]:
                print >> sys.stderr, self.db_name,'is a new database'
            self.nspam = 0
            self.nham = 0


class mySQLClassifier(SQLClassifier):
    '''Classifier object persisted in a mySQL database

    It is assumed that the database already exists, and that the mySQL
    server is currently running.'''
 
    def __init__(self, data_source_name):
        self.table_definition = ("create table bayes ("
                                 "  word varchar(255) not null default '',"
                                 "  nspam integer not null default 0,"
                                 "  nham integer not null default 0,"
                                 "  primary key(word)"
                                 ");")
        self.host = "localhost"
        self.username = "root"
        self.password = ""
        db_name = "spambayes"
        source_info = data_source_name.split()
        for info in source_info:
            if info.startswith("host"):
                self.host = info[5:]
            elif info.startswith("user"):
                self.username = info[5:]
            elif info.startswith("pass"):
                self.username = info[5:]
            elif info.startswith("dbname"):
                db_name = info[7:]
        SQLClassifier.__init__(self, db_name)

    def cursor(self):
        return self.db.cursor()

    def fetchall(self, c):
        return c.fetchall()

    def commit(self, c):
        self.db.commit()

    def load(self):
        '''Load state from database'''

        import MySQLdb
        
        if options["globals", "verbose"]:
            print >> sys.stderr, 'Loading state from',self.db_name,'database'

        self.db = MySQLdb.connect(host=self.host, db=self.db_name,
                                  user=self.username, passwd=self.password)

        c = self.cursor()
        try:
            c.execute("select count(*) from bayes")
        except MySQLdb.ProgrammingError:
            self.db.rollback()
            self.create_bayes()
        
        if self._has_key(self.statekey):
            row = self._get_row(self.statekey)
            self.nspam = int(row[1])
            self.nham = int(row[2])
            if options["globals", "verbose"]:
                print >> sys.stderr, ('%s is an existing database,'
                                      ' with %d spam and %d ham') \
                      % (self.db_name, self.nspam, self.nham)
        else:
            # new database
            if options["globals", "verbose"]:
                print >> sys.stderr, self.db_name,'is a new database'
            self.nspam = 0
            self.nham = 0

    def _wordinfoget(self, word):
        if isinstance(word, unicode):
            word = word.encode("utf-8")

        row = self._get_row(word)
        if row:
            item = self.WordInfoClass()
            item.__setstate__((row[1], row[2]))
            return item
        else:
            return None


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

        if options["globals", "verbose"]:
            print >> sys.stderr, 'training with',message.key()

        self.bayes.learn(message.tokenize(), self.is_spam)
#                         self.updateprobs)

    def onRemoveMessage(self, message):
        '''A message is being removed from an observed corpus.'''

        self.untrain(message)

    def untrain(self, message):
        '''Untrain the database with the message'''

        if options["globals", "verbose"]:
            print >> sys.stderr, 'untraining with',message.key()

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

class NoSuchClassifierError(Exception):
    def __init__(self, invalid_name):
        self.invalid_name = invalid_name
    def __str__(self):
        return repr(self.invalid_name)

# values are classifier class and True if it accepts a mode
# arg, False otherwise
_storage_types = {"dbm" : (DBDictClassifier, True),
                  "pickle" : (PickledClassifier, False),
                  "pgsql" : (PGClassifier, False),
                  "mysql" : (mySQLClassifier, False),
                  }

def open_storage(data_source_name, useDB=True, mode=None):
    """Return a storage object appropriate to the given parameters.

    By centralizing this code here, all the applications will behave
    the same given the same options.

    If useDB is false, a pickle will be used, otherwise if the data
    source name includes "::", whatever is before that determines
    the type of database.  If the source name doesn't include "::",
    then a DBDictClassifier is used."""
    if useDB:
        if data_source_name.find('::') != -1:
            db_type, rest = data_source_name.split('::', 1)
            if _storage_types.has_key(db_type.lower()):
                klass, supports_mode = _storage_types[db_type.lower()]
                data_source_name = rest
            else:
                raise NoSuchClassifierError(db_type)
        else:
            klass, supports_mode = _storage_types["dbm"]
    else:
        klass, supports_mode = _storage_types["pickle"]
    try:
        if supports_mode and mode is not None:
            return klass(data_source_name, mode)
        else:
            return klass(data_source_name)
    except dbmstorage.error, e:
        if str(e) == "No dbm modules available!":
            # We expect this to hit a fair few people, so warn them nicely,
            # rather than just printing the trackback.
            print >> sys.stderr, "\nYou do not have a dbm module available " \
                  "to use.  You need to either use a pickle (see the FAQ)" \
                  ", use Python 2.3 (or above), or install a dbm module " \
                  "such as bsddb (see http://sf.net/projects/pybsddb)."
            sys.exit()


if __name__ == '__main__':
    import sys
    print >> sys.stderr, __doc__
