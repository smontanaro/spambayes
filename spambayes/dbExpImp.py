#! /usr/bin/env python

"""dbExpImp.py - Bayes database export/import

Classes:


Abstract:

    This utility has the primary function of exporting and importing
    a spambayes database into/from a flat file.  This is useful in a number
    of scenarios.
    
    Platform portability of database - flat files can be exported and
    imported across platforms (winduhs and linux, for example)
    
    Database implementation changes - databases can survive database
    implementation upgrades or new database implementations.  For example,
    if a dbm implementation changes between python x.y and python x.y+1...
    
    Database reorganization - an export followed by an import reorgs an
    existing database, <theoretically> improving performance, at least in 
    some database implementations
    
    Database sharing - it is possible to distribute particular databases
    for research purposes, database sharing purposes, or for new users to
    have a 'seed' database to start with.
    
    Database merging - multiple databases can be merged into one quite easily
    by simply not specifying -n on an import.  This will add the two database
    nham and nspams together (assuming the two databases do not share corpora)
    and for wordinfo conflicts, will add spamcount and hamcount together.
    
    Spambayes software release migration - an export can be executed before
    a release upgrade, as part of the installation script.  Then, after the
    new software is installed, an import can be executed, which will
    effectively preserve existing training.  This eliminates the need for
    retraining every time a release is installed.
    
    Others?  I'm sure I haven't thought of everything...
    
Usage:
    dbExpImp [options]

        options:
            -e     : export
            -i     : import
            -v     : verbose mode (some additional diagnostic messages)
            -f: FN : flat file to export to or import from
            -d: FN : name of pickled database file to use
            -D: FN : name of dbm database file to use
            -m     : merge import into an existing database file.  This is
                     meaningful only for import. If omitted, a new database
                     file will be created.  If specified, the imported
                     wordinfo will be merged into an existing database.
                     Run dbExpImp -h for more information.
            -h     : help

Examples:

    Export pickled mybayes.db into mybayes.db.export as a csv flat file
        dbExpImp -e -d mybayes.db -f mybayes.db.export
        
    Import mybayes.eb.export into a new DBM mybayes.db
        dbExpImp -i -D mybayes.db -f mybayes.db.export
       
    Export, then import (reorganize) new pickled mybayes.db
        dbExpImp -e -i -n -d mybayes.db -f mybayes.db.export
        
    Convert a bayes database from pickle to DBM
        dbExpImp -e -d abayes.db -f abayes.export
        dbExpImp -i -D abayes.db -f abayes.export
        
    Create a new database (newbayes.db) from two
        databases (abayes.db, bbayes.db)
        dbExpImp -e -d abayes.db -f abayes.export
        dbExpImp -e -d bbayes.db -f bbayes.export
        dbExpImp -i -d newbayes.db -f abayes.export
        dbExpImp -i -m -d newbayes.db -f bbayes.export

To Do:
    o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    
from __future__ import generators

import spambayes.storage
from spambayes.Options import options
import sys, os, getopt, errno, re
import urllib

def runExport(dbFN, useDBM, outFN):

    if useDBM:
        bayes = spambayes.storage.DBDictClassifier(dbFN)
        words = bayes.db.keys()
        words.remove(bayes.statekey)
    else:
        bayes = spambayes.storage.PickledClassifier(dbFN)
        words = bayes.wordinfo.keys()

    try:
        fp = open(outFN, 'w')
    except IOError, e:
        if e.errno != errno.ENOENT:
           raise
       
    nham = bayes.nham;
    nspam = bayes.nspam;
    
    print "Exporting database %s to file %s" % (dbFN, outFN)
    print "Database has %s ham, %s spam, and %s words" \
            % (nham, nspam, len(words))
    
    fp.write("%s,%s,\n" % (nham, nspam))
    
    for word in words:
        wi = bayes._wordinfoget(word)
        hamcount = wi.hamcount
        spamcount = wi.spamcount
        word = urllib.quote(word)
        fp.write("%s`%s`%s`\n" % (word, hamcount, spamcount))
        
    fp.close()

def runImport(dbFN, useDBM, newDBM, inFN):

    if newDBM:
        try:
            os.unlink(dbFN)
        except OSError, e:
            if e.errno != 2:     # errno.<WHAT>
                raise
                
        try:
            os.unlink(dbFN+".dat")
        except OSError, e:
            if e.errno != 2:     # errno.<WHAT>
                raise
                
        try:
            os.unlink(dbFN+".dir")
        except OSError, e:
            if e.errno != 2:     # errno.<WHAT>
                raise
                
    if useDBM:
        bayes = spambayes.storage.DBDictClassifier(dbFN)
    else:
        bayes = spambayes.storage.PickledClassifier(dbFN)

    try:
        fp = open(inFN, 'r')
    except IOError, e:
        if e.errno != errno.ENOENT:
           raise
    
    nline = fp.readline()
    (nham, nspam, junk) = re.split(',', nline)
 
    if newDBM:
        bayes.nham = int(nham)
        bayes.nspam = int(nspam)
    else:
        bayes.nham += int(nham)
        bayes.nspam += int(nspam)
    
    if newDBM:
        impType = "Importing"
    else:
        impType = "Merging"
  
    print "%s database %s using file %s" % (impType, dbFN, inFN)

    lines = fp.readlines()
    
    for line in lines:
        (word, hamcount, spamcount, junk) = re.split('`', line)
        word = urllib.unquote(word)
       
        try:
            wi = bayes.wordinfo[word]
        except KeyError:
            wi = bayes.WordInfoClass()

        wi.hamcount += int(hamcount)
        wi.spamcount += int(spamcount)
               
        bayes._wordinfoset(word, wi)

    fp.close()

    print "Storing database, please be patient.  Even moderately large"
    print "databases may take a very long time to store."
    bayes.store()
    print "Finished storing database"
    
    if useDBM:
        words = bayes.db.keys()
        words.remove(bayes.statekey)
    else:
        words = bayes.wordinfo.keys()
        
    print "Database has %s ham, %s spam, and %s words" \
           % (bayes.nham, bayes.nspam, len(words))




if __name__ == '__main__':

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'iehmvd:D:f:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    usePickle = False
    useDBM = False
    newDBM = True
    dbFN = None
    flatFN = None
    exp = False
    imp = False

    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-d':
            useDBM = False
            dbFN = arg
        elif opt == '-D':
            useDBM = True
            dbFN = arg
        elif opt == '-f':
            flatFN = arg
        elif opt == '-e':
            exp = True
        elif opt == '-i':
            imp = True
        elif opt == '-m':
            newDBM = False
        elif opt == '-v':
            options.verbose = True

    if (dbFN and flatFN):
        if exp:
            runExport(dbFN, useDBM, flatFN)
        if imp:
            runImport(dbFN, useDBM, newDBM, flatFN)
    else:
        print >>sys.stderr, __doc__