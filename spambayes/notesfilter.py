#! /usr/bin/env python

'''notesfilter.py - Lotus Notes Spambayes interface.

Classes:

Abstract:

    This module uses Spambayes as a filter against a Lotus Notes mail
    database.  The Notes client must be running when this process is
    executed.
    
    It requires a Notes folder, named as a parameter, with four
    subfolders:
        Spam
        Ham
        Train as Spam
        Train as Ham
        
    It classifies mail that is in the inbox.  Mail that is classified
    as spam is moved to the Spam folder.  Mail that is to be trained
    as spam should be manually moved to that folder by the user.
    Likewise mail that is to be trained as ham.  After training, spam
    is moved to the Spam folder and ham is moved to the Ham folder.
    
    Because there is no programmatic way to determine if a particular
    mail has been previously processed by this classification program,
    it keeps a pickled dictionary of notes mail ids, so that once a
    mail has been classified, it will not be classified again.  The
    non-existence of is index file, named <local database>.'sbindex',
    indicates to the system that this is the first time it has been
    run.  Rather than classify the inbox in this case, the contents of
    the inbox are placed in the index to note the 'starting point' of
    the system.  After that, any new messages in the inbox are
    eligible for classification.

Usage:
    notesfilter [options]

	note: option values with spaces in them must be enclosed
	      in double quotes
	      
        options:
            -d  dbname  : pickled training database filename
            -D  dbname  : dbm training database filename
            -l  dbname  : database filename of local mail replica
                            e.g. localmail.nsf
            -r  server  : server address of the server mail database
                            e.g. d27ml602/27/M/IBM
                          if specified, will initiate a replication
            -f  folder  : Name of spambayes folder
                            must have subfolders: Spam
                                                  Ham
                                                  Train as Spam
                                                  Train as Ham
            -t          : train contents of Train as Spam and Train as Ham
            -c          : classify inbox
            -h          : help

Examples:

    Replicate and classify inbox
        notesfilter -c -d notesbayes -r mynoteserv -l mail.nsf -f Spambayes
        
    Train Spam and Ham, then classify inbox
        notesfilter -t -c -d notesbayes -l mail.nsf -f Spambayes
    
    Replicate, then classify inbox      
        notesfilter -c -d test7 -l mail.nsf -r nynoteserv -f Spambayes
 
To Do:
    o Dump/purge notesindex file
    o Show h:s ratio, make recommendations
    o Create correct folders if they do not exist
    o Options for some of this stuff?
    o pop3proxy style training/configuration interface?
    o Suggestions?
    '''

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "Mark Hammond, for his remarkable win32 module."

from __future__ import generators

try:
    True, False
except NameError:
    # Maintain compatibility with Python 2.2
    True, False = 1, 0
    def bool(val):
        return not not val

import sys
from spambayes import tokenizer, storage
from spambayes.Options import options
import cPickle as pickle
import errno
import win32com.client
import getopt


def classifyInbox(v, vmoveto, bayes, ldbname):

    # the notesindex hash ensures that a message is looked at only once

    try:
        fp = open("%s.sbindex" % (ldbname), 'rb')
    except IOError, e:
        if e.errno != errno.ENOENT: raise
        notesindex = {}
        print "notesindex file not found, this is a first time run"
        print "No classification will be performed"
        firsttime = 1
    else:
        notesindex = pickle.load(fp)
        fp.close()
        firsttime = 0

    docstomove = []
    numham = 0
    numspam = 0
    numuns = 0
    numdocs = 0
    doc = v.GetFirstDocument()
    while doc:
        nid = doc.NOTEID
        if firsttime:
           notesindex[nid] = 'never classified'
        else:
            if not notesindex.has_key(nid):

                numdocs += 1
                
                try:
                    subj = doc.GetItemValue('Subject')[0]
                except:
                    subj = 'No Subject'

                try:
                    body  = doc.GetItemValue('Body')[0]
                except:
                    body = 'No Body'

                message = "Subject: %s\r\n%s" % (subj, body)

                # generate_long_skips = True blows up on occ.
                options.generate_long_skips = False
                tokens = tokenizer.tokenize(message)
                prob, clues = bayes.spamprob(tokens, evidence=True)

                if prob < options.ham_cutoff:
                    disposition = options.header_ham_string
                    numham += 1
                elif prob > options.spam_cutoff:
                    disposition = options.header_spam_string
                    docstomove += [doc]
                    numspam += 1
                else:
                    disposition = options.header_unsure_string
                    numuns += 1

                notesindex[nid] = disposition

        doc = v.GetNextDocument(doc)

    for doc in docstomove:
        doc.RemoveFromFolder(v.Name)
        doc.PutInFolder(vmoveto.Name)

    print "%s documents processed" % (numdocs)
    print "   %s classified as spam" % (numspam)
    print "   %s classified as ham" % (numham)
    print "   %s classified as unsure" % (numuns)
    
    fp = open("timstone.nsf.sbindex", 'wb')
    pickle.dump(notesindex, fp)
    fp.close()

def processAndTrain(v, vmoveto, bayes, is_spam):

    if is_spam:
        str = "spam"
    else:
        str = "ham"

    print "Training %s" % (str)
    
    docstomove = []
    doc = v.GetFirstDocument()
    while doc:
        try:
            subj = doc.GetItemValue('Subject')[0]
        except:
            subj = 'No Subject'

        try:
            body  = doc.GetItemValue('Body')[0]
        except:
            body = 'No Body'
            
        message = "Subject: %s\r\n%s" % (subj, body)

        options.generate_long_skips = False
        tokens = tokenizer.tokenize(message)
        bayes.learn(tokens, is_spam)

        docstomove += [doc]

        doc = v.GetNextDocument(doc)

    for doc in docstomove:
        doc.RemoveFromFolder(v.Name)
        doc.PutInFolder(vmoveto.Name)

    print "%s documents trained" % (len(docstomove))

def run(bdbname, useDBM, ldbname, rdbname, foldname, doTrain, doClassify):

    if useDBM:
        bayes = storage.DBDictClassifier(bdbname)
    else:
        bayes = storage.PickledClassifier(bdbname)
    
    sess = win32com.client.Dispatch("Lotus.NotesSession")
    sess.initialize()
    db = sess.GetDatabase("",ldbname)
    
    vinbox = db.getView('($Inbox)')
    vspam = db.getView("%s\Spam" % (foldname))
    vham = db.getView("%s\Ham" % (foldname))
    vtrainspam = db.getView("%s\Train as Spam" % (foldname))
    vtrainham = db.getView("%s\Train as Ham" % (foldname))
    
    if rdbname:
        print "Replicating..."
        db.Replicate(rdbname)
        print "Done"
        
    if doTrain:
        processAndTrain(vtrainspam, vspam, bayes, True)
        # for some reason, using inbox as a target here loses the mail
        processAndTrain(vtrainham, vham, bayes, False)
        
    if doClassify:
        classifyInbox(vinbox, vspam, bayes, ldbname)
    
    bayes.store()

if __name__ == '__main__':

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htcd:D:l:r:f:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    bdbname = None  # bayes database name
    ldbname = None  # local notes database name
    rdbname = None  # remote notes database location
    sbfname = None  # spambayes folder name
    doTrain = False
    doClassify = False

    for opt, arg in opts:
        if opt == '-h':
            print >>sys.stderr, __doc__
            sys.exit()
        elif opt == '-d':
            useDBM = False
            bdbname = arg
        elif opt == '-D':
            useDBM = True
            bdbname = arg
        elif opt == '-l':
            ldbname = arg
        elif opt == '-r':
            rdbname = arg
        elif opt == '-f':
            sbfname = arg
        elif opt == '-t':
            doTrain = True
        elif opt == '-c':
            doClassify = True

    if (bdbname and ldbname and sbfname and (doTrain or doClassify)):
        run(bdbname, useDBM, ldbname, rdbname, \
            sbfname, doTrain, doClassify)
    else:
        print >>sys.stderr, __doc__