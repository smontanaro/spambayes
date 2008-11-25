#! /usr/bin/env python

'''storage.py - Spambayes database management framework.

Classes:
    PickledClassifier - Classifier that uses a pickle db
    DBDictClassifier - Classifier that uses a shelve db
    PGClassifier - Classifier that uses postgres
    mySQLClassifier - Classifier that uses mySQL
    CBDClassifier - Classifier that uses CDB
    ZODBClassifier - Classifier that uses ZODB
    ZEOClassifier - Classifier that uses ZEO
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
    o Suggestions?

    '''

# This module is part of the spambayes project, which is Copyright 2002-2007
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

import os
import sys
import time
import types
import tempfile
from spambayes import classifier
from spambayes.Options import options, get_pathname_option
import cPickle as pickle
import errno
import shelve
from spambayes import cdb
from spambayes import dbmstorage

# Make shelve use binary pickles by default.
oldShelvePickler = shelve.Pickler
def binaryDefaultPickler(f, binary=1):
    return oldShelvePickler(f, binary)
shelve.Pickler = binaryDefaultPickler

PICKLE_TYPE = 1
NO_UPDATEPROBS = False   # Probabilities will not be autoupdated with training
UPDATEPROBS = True       # Probabilities will be autoupdated with training

def safe_pickle(filename, value, protocol=0):
    '''Store value as a pickle without creating corruption'''

    # Be as defensive as possible.  Always keep a safe copy.
    tmp = filename + '.tmp'
    fp = None
    try: 
        fp = open(tmp, 'wb') 
        pickle.dump(value, fp, protocol) 
        fp.close() 
    except IOError, e: 
        if options["globals", "verbose"]: 
            print >> sys.stderr, 'Failed update: ' + str(e)
        if fp is not None: 
            os.remove(tmp) 
        raise
    try:
        # With *nix we can just rename, and (as long as permissions
        # are correct) the old file will vanish.  With win32, this
        # won't work - the Python help says that there may not be
        # a way to do an atomic replace, so we rename the old one,
        # put the new one there, and then delete the old one.  If
        # something goes wrong, there is at least a copy of the old
        # one.
        os.rename(tmp, filename)
    except OSError:
        os.rename(filename, filename + '.bak')
        os.rename(tmp, filename)
        os.remove(filename + '.bak')
    
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

        safe_pickle(self.db_name, self, PICKLE_TYPE)

    def close(self):
        # we keep no resources open - nothing to do
        pass

# Values for our changed words map
WORD_DELETED = "D"
WORD_CHANGED = "C"

STATE_KEY = 'saved state'

class DBDictClassifier(classifier.Classifier):
    '''Classifier object persisted in a caching database'''

    def __init__(self, db_name, mode='c'):
        '''Constructor(database name)'''

        classifier.Classifier.__init__(self)
        self.statekey = STATE_KEY
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
        # but we do anyway, because it makes it more clear what has gone
        # wrong if we try to keep using the database after we have closed
        # it.
        if hasattr(self, "db"):
            del self.db
        if hasattr(self, "dbm"):
            del self.dbm
        if options["globals", "verbose"]:
            print >> sys.stderr, 'Closed',self.db_name,'database'

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
        self.statekey = STATE_KEY
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
        return [r[0] for r in rows]


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

        self.db = psycopg.connect('dbname=' + self.db_name)

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
        self.charset = None
        source_info = data_source_name.split()
        for info in source_info:
            if info.startswith("host"):
                self.host = info[5:]
            elif info.startswith("user"):
                self.username = info[5:]
            elif info.startswith("pass"):
                self.password = info[5:]
            elif info.startswith("dbname"):
                db_name = info[7:]
            elif info.startswith("charset"):
                self.charset = info[8:]
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

        params = {
          'host': self.host, 'db': self.db_name,
          'user': self.username, 'passwd': self.password,
          'charset': self.charset
        }
        self.db = MySQLdb.connect(**params)

        c = self.cursor()
        try:
            c.execute("select count(*) from bayes")
        except MySQLdb.ProgrammingError:
            try:
                self.db.rollback()
            except MySQLdb.NotSupportedError:
                # Server doesn't support rollback, so just assume that
                # we can keep going and create the db.  This should only
                # happen once, anyway.
                pass
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


class CDBClassifier(classifier.Classifier):
    """A classifier that uses a CDB database.

    A CDB wordinfo database is quite small and fast but is slow to update.
    It is appropriate if training is done rarely (e.g. monthly or weekly
    using archived ham and spam).
    """
    def __init__(self, db_name):
        classifier.Classifier.__init__(self)
        self.db_name = db_name
        self.statekey = STATE_KEY
        self.load()

    def _WordInfoFactory(self, counts):
        # For whatever reason, WordInfo's cannot be created with
        # constructor ham/spam counts, so we do the work here.
        # Since we're doing the work, we accept the ham/spam count
        # in the form of a comma-delimited string, as that's what
        # we get.
        ham, spam = counts.split(',')
        wi = classifier.WordInfo()
        wi.hamcount = int(ham)
        wi.spamcount = int(spam)
        return wi

    # Stolen from sb_dbexpimp.py
    # Heaven only knows what encoding non-ASCII stuff will be in
    # Try a few common western encodings and punt if they all fail
    def uunquote(self, s):
        for encoding in ("utf-8", "cp1252", "iso-8859-1"):
            try:
                return unicode(s, encoding)
            except UnicodeDecodeError:
                pass
        # punt
        return s

    def load(self):
        if os.path.exists(self.db_name):
            db = open(self.db_name, "rb")
            data = dict(cdb.Cdb(db))
            db.close()
            self.nham, self.nspam = [int(i) for i in \
                                     data[self.statekey].split(',')]
            self.wordinfo = dict([(self.uunquote(k),
                                   self._WordInfoFactory(v)) \
                                  for k, v in data.iteritems() \
                                      if k != self.statekey])
            if options["globals", "verbose"]:
                print >> sys.stderr, ('%s is an existing CDB,'
                                      ' with %d ham and %d spam') \
                                      % (self.db_name, self.nham,
                                         self.nspam)
        else:
            if options["globals", "verbose"]:
                print >> sys.stderr, self.db_name, 'is a new CDB'
            self.wordinfo = {}
            self.nham = 0
            self.nspam = 0

    def store(self):
        items = [(self.statekey, "%d,%d" % (self.nham, self.nspam))]
        for word, wi in self.wordinfo.iteritems():
            if isinstance(word, types.UnicodeType):
                word = word.encode("utf-8")
            items.append((word, "%d,%d" % (wi.hamcount, wi.spamcount)))
        db = open(self.db_name, "wb")
        cdb.cdb_make(db, items)
        db.close()

    def close(self):
        # We keep no resources open - nothing to do.
        pass


# If ZODB isn't available, then this class won't be useable, but we
# still need to be able to import this module.  So we pretend that all
# is ok.
try:
    from persistent import Persistent
except ImportError:
    try:
        from ZODB import Persistent
    except ImportError:
        Persistent = object

class _PersistentClassifier(classifier.Classifier, Persistent):
    def __init__(self):
        import ZODB
        from BTrees.OOBTree import OOBTree

        classifier.Classifier.__init__(self)
        self.wordinfo = OOBTree()

class ZODBClassifier(object):
    # Allow subclasses to override classifier class.
    ClassifierClass = _PersistentClassifier

    def __init__(self, db_name, mode='c'):
        self.db_filename = db_name
        self.db_name = os.path.basename(db_name)
        self.closed = True
        self.mode = mode
        self.load()

    def __getattr__(self, att):
        # We pretend that we are a classifier subclass.
        if hasattr(self, "classifier") and hasattr(self.classifier, att):
            return getattr(self.classifier, att)
        raise AttributeError("ZODBClassifier object has no attribute '%s'"
                             % (att,))

    def __setattr__(self, att, value):
        # For some attributes, we change the classifier instead.
        if att in ("nham", "nspam") and hasattr(self, "classifier"):
            setattr(self.classifier, att, value)
        else:
            object.__setattr__(self, att, value)

    def create_storage(self):
        import ZODB
        from ZODB.FileStorage import FileStorage
        try:
            self.storage = FileStorage(self.db_filename,
                                       read_only=self.mode=='r')
        except IOError, msg:
            print >> sys.stderr, ("Could not create FileStorage from",
                                  self.db_filename)
            raise

    def load(self):
        '''Load state from database'''
        import ZODB

        if options["globals", "verbose"]:
            print >> sys.stderr, "Loading state from %s (%s) database" % \
                  (self.db_filename, self.db_name)

        # If we are not closed, then we need to close first before we
        # reload.
        if not self.closed:
            self.close()

        self.create_storage()
        self.DB = ZODB.DB(self.storage, cache_size=10000)
        self.conn = self.DB.open()
        root = self.conn.root()

        self.classifier = root.get(self.db_name)
        if self.classifier is None:
            # There is no classifier, so create one.
            if options["globals", "verbose"]:
                print >> sys.stderr, self.db_name, 'is a new ZODB'
            self.classifier = root[self.db_name] = self.ClassifierClass()
        else:
            if options["globals", "verbose"]:
                print >> sys.stderr, '%s is an existing ZODB, with %d ' \
                      'ham and %d spam' % (self.db_name, self.nham,
                                           self.nspam)
        self.closed = False

    def store(self):
        '''Place state into persistent store'''
        try:
            import ZODB
            import ZODB.Transaction
        except ImportError:
            import transaction
            commit = transaction.commit
            abort = transaction.abort
        else:
            commit = ZODB.Transaction.get_transaction().commit
            abort = ZODB.Transaction.get_transaction().abort
        from ZODB.POSException import ConflictError
        try:
            from ZODB.POSException import TransactionFailedError
        except:
            from ZODB.POSException import TransactionError as TransactionFailedError
        from ZODB.POSException import ReadOnlyError

        assert not self.closed, "Can't store a closed database"

        if options["globals", "verbose"]:
            print >> sys.stderr, 'Persisting', self.db_name, 'state in database'

        try:
            commit()
        except ConflictError:
            # We'll save it next time, or on close.  It'll be lost if we
            # hard-crash, but that's unlikely, and not a particularly big
            # deal.
            if options["globals", "verbose"]:
                print >> sys.stderr, "Conflict on commit", self.db_name
            abort()
        except TransactionFailedError:
            # Saving isn't working.  Try to abort, but chances are that
            # restarting is needed.
            print >> sys.stderr, "Storing failed.  Need to restart.", \
                  self.db_name
            abort()
        except ReadOnlyError:
            print >> sys.stderr, "Can't store transaction to read-only db."
            abort()

    def close(self, pack=True, retain_backup=True):
        # Ensure that the db is saved before closing.  Alternatively, we
        # could abort any waiting transaction.  We need to do *something*
        # with it, though, or it will be still around after the db is
        # closed and cause problems.  For now, saving seems to make sense
        # (and we can always add abort methods if they are ever needed).
        if self.mode != 'r':
            self.store()

        # We don't make any use of the 'undo' capabilities of the
        # FileStorage at the moment, so might as well pack the database
        # each time it is closed, to save as much disk space as possible.
        # Pack it up to where it was 'yesterday'.
        if pack and self.mode != 'r':
            self.pack(time.time()-60*60*24, retain_backup)

        # Do the closing.        
        self.DB.close()
        self.storage.close()

        # Ensure that we cannot continue to use this classifier.
        delattr(self, "classifier")

        self.closed = True
        if options["globals", "verbose"]:
            print >> sys.stderr, 'Closed', self.db_name, 'database'

    def pack(self, t, retain_backup=True):
        """Like FileStorage pack(), but optionally remove the .old
        backup file that is created.  Often for our purposes we do
        not care about being able to recover from this.  Also
        ignore the referencesf parameter, which appears to not do
        anything."""
        if hasattr(self.storage, "pack"):
            self.storage.pack(t, None)
        if not retain_backup:
            old_name = self.db_filename + ".old"
            if os.path.exists(old_name):
                os.remove(old_name)


class ZEOClassifier(ZODBClassifier):
    def __init__(self, data_source_name):
        source_info = data_source_name.split()
        self.host = "localhost"
        self.port = None
        db_name = "SpamBayes"
        self.username = ''
        self.password = ''
        self.storage_name = '1'
        self.wait = None
        self.wait_timeout = None
        for info in source_info:
            if info.startswith("host"):
                try:
                    # ZEO only accepts strings, not unicode.
                    self.host = str(info[5:])
                except UnicodeDecodeError, e:
                    print >> sys.stderr, "Couldn't set host", \
                          info[5:], str(e)
            elif info.startswith("port"):
                self.port = int(info[5:])
            elif info.startswith("dbname"):
                db_name = info[7:]
            elif info.startswith("user"):
                self.username = info[5:]
            elif info.startswith("pass"):
                self.password = info[5:]
            elif info.startswith("storage_name"):
                self.storage_name = info[13:]
            elif info.startswith("wait_timeout"):
                self.wait_timeout = int(info[13:])
            elif info.startswith("wait"):
                self.wait = info[5:] == "True"
        ZODBClassifier.__init__(self, db_name)

    def create_storage(self):
        from ZEO.ClientStorage import ClientStorage
        if self.port:
            addr = self.host, self.port
        else:
            addr = self.host
        if options["globals", "verbose"]:
            print >> sys.stderr, "Connecting to ZEO server", addr, \
                  self.username, self.password
        # Use persistent caches, with the cache in the temp directory.
        # If the temp directory is cleared out, we lose the cache, but
        # that doesn't really matter, and we should always be able to
        # write to it.
        try:
            self.storage = ClientStorage(addr, name=self.db_name,
                                         read_only=self.mode=='r',
                                         username=self.username,
                                         client=self.db_name,
                                         wait=self.wait,
                                         wait_timeout=self.wait_timeout,
                                         storage=self.storage_name,
                                         var=tempfile.gettempdir(),
                                         password=self.password)
        except ValueError:
            # Probably bad cache; remove it and try without the cache.
            try:
                os.remove(os.path.join(tempfile.gettempdir(),
                                       self.db_name + \
                                       self.storage_name + ".zec"))
            except OSError:
                pass
            self.storage = ClientStorage(addr, name=self.db_name,
                                         read_only=self.mode=='r',
                                         username=self.username,
                                         wait=self.wait,
                                         wait_timeout=self.wait_timeout,
                                         storage=self.storage_name,
                                         password=self.password)

    def is_connected(self):
        return self.storage.is_connected()


# Flags that the Trainer will recognise.  These should be or'able integer
# values (i.e. 1, 2, 4, 8, etc.).
NO_TRAINING_FLAG = 1

class Trainer(object):
    '''Associates a Classifier object and one or more Corpora, \
    is an observer of the corpora'''

    def __init__(self, bayes, is_spam, updateprobs=NO_UPDATEPROBS):
        '''Constructor(Classifier, is_spam(True|False),
        updateprobs(True|False)'''

        self.bayes = bayes
        self.is_spam = is_spam
        self.updateprobs = updateprobs

    def onAddMessage(self, message, flags=0):
        '''A message is being added to an observed corpus.'''
        if not (flags & NO_TRAINING_FLAG):
            self.train(message)

    def train(self, message):
        '''Train the database with the message'''

        if options["globals", "verbose"]:
            print >> sys.stderr, 'training with ', message.key()

        self.bayes.learn(message.tokenize(), self.is_spam)
        message.setId(message.key())
        message.RememberTrained(self.is_spam)

    def onRemoveMessage(self, message, flags=0):
        '''A message is being removed from an observed corpus.'''
        # If a message is being expired from the corpus, we do
        # *NOT* want to untrain it, because that's not what's happening.
        # If this is the case, then flags will include NO_TRAINING_FLAG.
        # There are no other flags we currently use.
        if not (flags & NO_TRAINING_FLAG):
            self.untrain(message)

    def untrain(self, message):
        '''Untrain the database with the message'''

        if options["globals", "verbose"]:
            print >> sys.stderr, 'untraining with',message.key()

        self.bayes.unlearn(message.tokenize(), self.is_spam)
#                           self.updateprobs)
        # can raise ValueError if database is fouled.  If this is the case,
        # then retraining is the only recovery option.
        message.RememberTrained(None)

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

class MutuallyExclusiveError(Exception):
    def __str__(self):
        return "Only one type of database can be specified"

# values are classifier class, True if it accepts a mode
# arg, and True if the argument is a pathname
_storage_types = {"dbm" : (DBDictClassifier, True, True),
                  "pickle" : (PickledClassifier, False, True),
                  "pgsql" : (PGClassifier, False, False),
                  "mysql" : (mySQLClassifier, False, False),
                  "cdb" : (CDBClassifier, False, True),
                  "zodb" : (ZODBClassifier, True, True),
                  "zeo" : (ZEOClassifier, False, False),
                  }

def open_storage(data_source_name, db_type="dbm", mode=None):
    """Return a storage object appropriate to the given parameters.

    By centralizing this code here, all the applications will behave
    the same given the same options.
    """
    try:
        klass, supports_mode, unused = _storage_types[db_type]
    except KeyError:
        raise NoSuchClassifierError(db_type)
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
        raise

# The different database types that are available.
# The key should be the command-line switch that is used to select this
# type, and the value should be the name of the type (which
# must be a valid key for the _storage_types dictionary).
_storage_options = { "-p" : "pickle",
                     "-d" : "dbm",
                     }

def database_type(opts, default_type=("Storage", "persistent_use_database"),
                  default_name=("Storage", "persistent_storage_file")):
    """Return the name of the database and the type to use.  The output of
    this function can be used as the db_type parameter for the open_storage
    function, for example:

        [standard getopts code]
        db_name, db_type = database_type(opts)
        storage = open_storage(db_name, db_type)

    The selection is made based on the options passed, or, if the
    appropriate options are not present, the options in the global
    options object.

    Currently supports:
       -p  :  pickle
       -d  :  dbm
    """
    nm, typ = None, None
    for opt, arg in opts:
        if _storage_options.has_key(opt):
            if nm is None and typ is None:
                nm, typ = arg, _storage_options[opt]
            else:
                raise MutuallyExclusiveError()
    if nm is None and typ is None:
        typ = options[default_type]
        try:
            unused, unused, is_path = _storage_types[typ]
        except KeyError:
            raise NoSuchClassifierError(db_type)
        if is_path:
            nm = get_pathname_option(*default_name)
        else:
            nm = options[default_name]
    return nm, typ

def convert(old_name=None, old_type=None, new_name=None, new_type=None):
    # The expected need is to convert the existing hammie.db dbm
    # database to a hammie.fs ZODB database.
    if old_name is None:
        old_name = "hammie.db"
    if old_type is None:
        old_type = "dbm"
    if new_name is None or new_type is None:
        auto_name, auto_type = database_type({})
        if new_name is None:
            new_name = auto_name
        if new_type is None:
            new_type = auto_type

    old_bayes = open_storage(old_name, old_type, 'r')
    new_bayes = open_storage(new_name, new_type)
    words = old_bayes._wordinfokeys()

    try:
        new_bayes.nham = old_bayes.nham
    except AttributeError:
        new_bayes.nham = 0
    try:
        new_bayes.nspam = old_bayes.nspam
    except AttributeError:
        new_bayes.nspam = 0

    print >> sys.stderr, "Converting %s (%s database) to " \
          "%s (%s database)." % (old_name, old_type, new_name, new_type)
    print >> sys.stderr, "Database has %s ham, %s spam, and %s words." % \
          (new_bayes.nham, new_bayes.nspam, len(words))

    for word in words:
        new_bayes._wordinfoset(word, old_bayes._wordinfoget(word))
    old_bayes.close()

    print >> sys.stderr, "Storing database, please be patient..."
    new_bayes.store()
    print >> sys.stderr, "Conversion complete."
    new_bayes.close()

def ensureDir(dirname):
    """Ensure that the given directory exists - in other words, if it
    does not exist, attempt to create it."""
    try:
        os.mkdir(dirname)
        if options["globals", "verbose"]:
            print >>sys.stderr, "Creating directory", dirname
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise

if __name__ == '__main__':
    print >> sys.stderr, __doc__
