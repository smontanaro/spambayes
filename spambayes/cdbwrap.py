#! /usr/bin/env python

import cdb
import tempfile
import struct
import time
import os
import shelve
from sets import Set

class DELITEM:
    # Special class to signify a deleted item
    pass

class CDBDict:
    def __init__(self, filename):
        self.filename = filename
        try:
            self.fp = open(filename, "rb")
            self.db = cdb.Cdb(self.fp)
        except:
            self.fp = None
            self.db = {}
        self.cache = {}
        self.newkeys = []

    def __delitem__(self, key):
        self[key] = DELITEM

    def __getitem__(self, key):
        val = self.cache.get(key)
        if val is DELITEM:
            raise KeyError, key
        if not val and self.db:
            val = self.db[key]
        return val

    def __setitem__(self, key, val):
        self.cache[key] = val
        if not self.db.get(key):
            self.newkeys.append(key)

    def __del__(self):
        if self.cache:
            import cdb
            
            if 1:
                newf = "%s.txt" % self.filename
                fp = open(newf, "wb")
                for key,value in self.iteritems():
                    fp.write("+%d,%d:%s->%s\n" % (len(key), len(value), key, value))
                fp.write("\n")
                fp.close()
                
            else:
                # XXX: security risk, but how to do this without the symlink
                # problem?
                newf = "%s-%f" % (self.filename, time.time())
                fp = open(newf, "wb")
                cdb.cdb_make(fp, self.iteritems())
                fp.close()
                os.rename(newf, self.filename)
    
    def __iter__(self, fn=lambda k,v: (k,v)):
        for key in self.newkeys:
            val = self.cache[key]
            if val is DELITEM:
                continue
            else:
                yield fn(key, val)
        for key,val in self.db.iteritems():
            nval = self.cache.get(key)
            if nval:
                if nval is DELITEM:
                    continue
                else:
                    yield fn(key, nval)
            else:
                yield fn(key, val)

    def __contains__(self, key):
        return self.has_key(key)

    def iteritems(self):
        return self.__iter__()

    def iterkeys(self):
        return self.__iter__(lambda k,v: k)

    def itervalues(self):
        return self.__iter__(lambda k,v: v)

    def items(self):
        ret = []
        for i in self.iteritems():
            ret.append(i)
        return ret

    def keys(self):
        ret = []
        for i in self.iterkeys():
            ret.append(i)
        return ret

    def values(self):
        ret = []
        for i in self.itervalues():
            ret.append(i)
        return ret

    def get(self, key, default=None):
        try:
            val = self[key]
        except KeyError:
            val = default
        return val

    def has_key(self, key):
        return self.get(key) and True

class CDBShelf(shelve.Shelf):
    """Shelf implementation using a Constant Database.
    
    This is initialized with the filename for the CDB database.  See the
    shelf module's __doc__ string for an overview of the interface.

    """
    
    def __init__(self, filename, flag='c'):
        db = CDBDict(filename)
        shelve.Shelf.__init__(self, db)
        

def test_shelf():
    s = CDBShelf("shelf.cdb")

    print "foo ->", s.get("foo")

    s["foo"] = s.get("foo", 1.0) + .1
    print "foo ->", s.get("foo")
    

def test_dict():
    db = CDBDict("services.cdb")

    one = db.get("1")
    if one:
        print 'db["1"] == %s; deleting' % one
        del db["1"]
    else:
        print 'db["1"] not set; setting'
        db["1"] = "One"

    print "New value is", db.get("1")

if __name__ == "__main__":
    test_shelf()
    test_dict()
