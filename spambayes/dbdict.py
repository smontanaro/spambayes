#! /usr/bin/env python

"""DBDict.py - Dictionary access to anydbm

Classes:
    DBDict - wraps an anydbm file

Abstract:
    DBDict class wraps an anydbm file with a reasonably complete set
    of dictionary access methods.  DBDicts can be iterated like a dictionary.
    
    The constructor accepts a class name which is used specifically to
    to pickle/unpickle an instance of that class.  When an instance of
    that class is being pickled, the pickler (actually __getstate__) prepends
    a 'W' to the pickled string, and when the unpickler (really __setstate__)
    encounters that 'W', it constructs that class (with no constructor
    arguments) and executes __setstate__ on the constructed instance.

    DBDict accepts an iterskip operand on the constructor.  This is a tuple
    of hash keys that will be skipped (not seen) during iteration.  This
    is for iteration only.  Methods such as keys() will return the entire
    complement of keys in the dbm hash, even if they're in iterskip.  An
    iterkeys() method is provided for iterating with skipped keys, and
    itervaluess() is provided for iterating values with skipped keys.

        >>> d = DBDict('/tmp/goober.db', MODE_CREATE, ('skipme', 'skipmetoo'))
        >>> d['skipme'] = 'booga'
        >>> d['countme'] = 'wakka'
        >>> print d.keys()
        ['skipme', 'countme']
        >>> for k in d.iterkeys():
        ...     print k
        countme
        >>> for v in d.itervalues():
        ...     print v
        wakka
        >>> for k,v in d.iteritems():
        ...     print k,v
        countme wakka

To Do:
    """

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Neale Pickett <neale@woozle.org>, \
              Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "Tim Peters (author of DBDict class), \
               all the spambayes contributors."

try:
    import cPickle as pickle
except ImportError:
    import pickle

import anydbm
import errno
import copy
import shutil
import os

MODE_CREATE = 'c'       # create file if necessary, open for readwrite
MODE_NEW = 'n'          # always create new file, open for readwrite
MODE_READWRITE = 'w'    # open existing file for readwrite
MODE_READONLY = 'r'     # open existing file for read only


class DBDict:
    """Database Dictionary.

    This wraps an anydbm database to make it look even more like a
    dictionary, much like the built-in shelf class.  The difference is
    that a DBDict supports all dict methods.

    Call it with the database.  Optionally, you can specify a list of
    keys to skip when iterating.  This only affects iterators; things
    like .keys() still list everything.  For instance:

    >>> d = DBDict('goober.db', MODE_CREATE, ('skipme', 'skipmetoo'))
    >>> d['skipme'] = 'booga'
    >>> d['countme'] = 'wakka'
    >>> print d.keys()
    ['skipme', 'countme']
    >>> for k in d.iterkeys():
    ...     print k
    countme

    """

    def __init__(self, dbname, mode, wclass, iterskip=()):
        self.hash = anydbm.open(dbname, mode)
        if not iterskip:
            self.iterskip = iterskip
        else:
            self.iterskip = ()
        self.wclass=wclass

    def __getitem__(self, key):
        v = self.hash[key]
        if v[0] == 'W':
            val = pickle.loads(v[1:])
            # We could be sneaky, like pickle.Unpickler.load_inst,
            # but I think that's overly confusing.
            obj = self.wclass()
            obj.__setstate__(val)
            return obj
        else:
            return pickle.loads(v)

    def __setitem__(self, key, val):
        if isinstance(val, self.wclass):
            val = val.__getstate__()
            v = 'W' + pickle.dumps(val, 1)
        else:
            v = pickle.dumps(val, 1)
        self.hash[key] = v

    def __getitem__(self, key):
        return pickle.loads(self.hash[key])

    def __setitem__(self, key, val):
        self.hash[key] = pickle.dumps(val, 1)

    def __delitem__(self, key, val):
        del(self.hash[key])

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

open = DBDict

def _test():
    import doctest
    import dbdict

    doctest.testmod(dbdict)

if __name__ == '__main__':
    _test()

