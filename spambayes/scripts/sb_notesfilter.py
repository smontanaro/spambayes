#! /usr/bin/env python

'''sb_notesfilter.py - Lotus Notes Spambayes interface.

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

    Depending on the execution parameters, it will do any or all of the
    following steps, in the order given.

    1. Train Spam from the Train as Spam folder (-t option)
    2. Train Ham from the Train as Ham folder (-t option)
    3. Replicate (-r option)
    4. Classify the inbox (-c option)
        
    Mail that is to be trained as spam should be manually moved to
    that folder by the user. Likewise mail that is to be trained as
    ham.  After training, spam is moved to the Spam folder and ham is
    moved to the Ham folder.

    Replication takes place if a remote server has been specified.
    This step may take a long time, depending on replication
    parameters and how much information there is to download, as well
    as line speed and server load.  Please be patient if you run with
    replication.  There is currently no progress bar or anything like
    that to tell you that it's working, but it is and will complete
    eventually.  There is also no mechanism for notifying you that the
    replication failed.  If it did, there is no harm done, and the program
    will continue execution.

    Mail that is classified as Spam is moved from the inbox to the
    Train as Spam folder.  You should occasionally review your Spam
    folder for Ham that has mistakenly been classified as Spam.  If
    there is any there, move it to the Train as Ham folder, so
    Spambayes will be less likely to make this mistake again.

    Mail that is classified as Ham or Unsure is left in the inbox.
    There is currently no means of telling if a mail was classified as
    Ham or Unsure.

    You should occasionally select some Ham and move it to the Train
    as Ham folder, so Spambayes can tell the difference between Spam
    and Ham. The goal is to maintain a relative balance between the
    number of Spam and the number of Ham that have been trained into
    the database. These numbers are reported every time this program
    executes.  However, if the amount of Spam you receive far exceeds
    the amount of Ham you receive, it may be very difficult to
    maintain this balance.  This is not a matter of great concern.
    Spambayes will still make very few mistakes in this circumstance.
    But, if this is the case, you should review your Spam folder for
    falsely classified Ham, and retrain those that you find, on a
    regular basis.  This will prevent statistical error accumulation,
    which if allowed to continue, would cause Spambayes to tend to
    classify everything as Spam.
    
    Because there is no programmatic way to determine if a particular
    mail has been previously processed by this classification program,
    it keeps a pickled dictionary of notes mail ids, so that once a
    mail has been classified, it will not be classified again.  The
    non-existence of is index file, named <local database>.sbindex,
    indicates to the system that this is an initialization execution.
    Rather than classify the inbox in this case, the contents of the
    inbox are placed in the index to note the 'starting point' of the
    system.  After that, any new messages in the inbox are eligible
    for classification.

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
            -p          : prompt "Press Enter to end" before ending
                          This is useful for automated executions where the
                          statistics output would otherwise be lost when the
                          window closes.

Examples:

    Replicate and classify inbox
        notesfilter -c -d notesbayes -r mynoteserv -l mail.nsf -f Spambayes
        
    Train Spam and Ham, then classify inbox
        notesfilter -t -c -d notesbayes -l mail.nsf -f Spambayes
    
    Replicate, then classify inbox      
        notesfilter -c -d test7 -l mail.nsf -r nynoteserv -f Spambayes
 
To Do:
    o Dump/purge notesindex file
    o Create correct folders if they do not exist
    o Options for some of this stuff?
    o pop3proxy style training/configuration interface?
    o parameter to retrain?
    o Suggestions?
    '''

# This module is part of the spambayes project, which is Copyright 2002
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__author__ = "Tim Stone <tim@fourstonesExpressions.com>"
__credits__ = "Mark Hammond, for his remarkable win32 modules."

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
import pywintypes
import getopt


def classifyInbox(v, vmoveto, bayes, ldbname, notesindex):

    # the notesindex hash ensures that a message is looked at only once

    if len(notesindex.keys()) == 0:
        firsttime = 1
    else:
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

                # Notes returns strings in unicode, and the Python
                # uni-decoder has trouble with these strings when
                # you try to print them.  So don't...

                # The com interface returns basic data types as tuples
                # only, thus the subscript on GetItemValue
                
                try:
                    subj = doc.GetItemValue('Subject')[0]
                except:
                    subj = 'No Subject'

                try:
                    body  = doc.GetItemValue('Body')[0]
                except:
                    body = 'No Body'

                message = "Subject: %s\r\n\r\n%s" % (subj, body)

                # generate_long_skips = True blows up on occasion,
                # probably due to this unicode problem.
                options["Tokenizer", "generate_long_skips"] = False
                tokens = tokenizer.tokenize(message)
                prob, clues = bayes.spamprob(tokens, evidence=True)

                if prob < options["Categorization", "ham_cutoff"]:
                    disposition = options["Hammie", "header_ham_string"]
                    numham += 1
                elif prob > options["Categorization", "spam_cutoff"]:
                    disposition = options["Hammie", "header_spam_string"]
                    docstomove += [doc]
                    numspam += 1
                else:
                    disposition = options["Hammie", "header_unsure_string"]
                    numuns += 1

                notesindex[nid] = 'classified'
                try:
                    print "%s spamprob is %s" % (subj[:30], prob)
                except UnicodeError:
                    print "<subject not printed> spamprob is %s" % (prob)

        doc = v.GetNextDocument(doc)

    # docstomove list is built because moving documents in the middle of
    # the classification loop looses the iterator position
    for doc in docstomove:
        doc.RemoveFromFolder(v.Name)
        doc.PutInFolder(vmoveto.Name)

    print "%s documents processed" % (numdocs)
    print "   %s classified as spam" % (numspam)
    print "   %s classified as ham" % (numham)
    print "   %s classified as unsure" % (numuns)
    

def processAndTrain(v, vmoveto, bayes, is_spam, notesindex):

    if is_spam:
        str = options["Hammie", "header_spam_string"]
    else:
        str = options["Hammie", "header_ham_string"]

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

        options["Tokenizer", "generate_long_skips"] = False
        tokens = tokenizer.tokenize(message)

        nid = doc.NOTEID
        if notesindex.has_key(nid):
            trainedas = notesindex[nid]
            if trainedas == options["Hammie", "header_spam_string"] and \
               not is_spam:
                # msg is trained as spam, is to be retrained as ham
                bayes.unlearn(tokens, True)
            elif trainedas == options["Hammie", "header_ham_string"] and \
                 is_spam:
                # msg is trained as ham, is to be retrained as spam
                bayes.unlearn(tokens, False)
  
        bayes.learn(tokens, is_spam)

        notesindex[nid] = str
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

    try:
        fp = open("%s.sbindex" % (ldbname), 'rb')
    except IOError, e:
        if e.errno != errno.ENOENT: raise
        notesindex = {}
        print "%s.sbindex file not found, this is a first time run" \
              % (ldbname)
        print "No classification will be performed"
    else:
        notesindex = pickle.load(fp)
        fp.close()
     
    sess = win32com.client.Dispatch("Lotus.NotesSession")
    try:
        sess.initialize()
    except pywintypes.com_error:
        print "Session aborted"
        sys.exit()
        
    db = sess.GetDatabase("",ldbname)
    
    vinbox = db.getView('($Inbox)')
    vspam = db.getView("%s\Spam" % (foldname))
    vham = db.getView("%s\Ham" % (foldname))
    vtrainspam = db.getView("%s\Train as Spam" % (foldname))
    vtrainham = db.getView("%s\Train as Ham" % (foldname))
    
    if doTrain:
        processAndTrain(vtrainspam, vspam, bayes, True, notesindex)
        # for some reason, using inbox as a target here loses the mail
        processAndTrain(vtrainham, vham, bayes, False, notesindex)
        
    if rdbname:
        print "Replicating..."
        db.Replicate(rdbname)
        print "Done"
        
    if doClassify:
        classifyInbox(vinbox, vtrainspam, bayes, ldbname, notesindex)

    print "The Spambayes database currently has %s Spam and %s Ham" \
        % (bayes.nspam, bayes.nham)

    bayes.store()

    fp = open("%s.sbindex" % (ldbname), 'wb')
    pickle.dump(notesindex, fp)
    fp.close()
    

if __name__ == '__main__':

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'htcpd:D:l:r:f:')
    except getopt.error, msg:
        print >>sys.stderr, str(msg) + '\n\n' + __doc__
        sys.exit()

    bdbname = None  # bayes database name
    ldbname = None  # local notes database name
    rdbname = None  # remote notes database location
    sbfname = None  # spambayes folder name
    doTrain = False
    doClassify = False
    doPrompt = False

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
        elif opt == '-p':
            doPrompt = True

    if (bdbname and ldbname and sbfname and (doTrain or doClassify)):
        run(bdbname, useDBM, ldbname, rdbname, \
            sbfname, doTrain, doClassify)

        if doPrompt:
            try:
                key = input("Press Enter to end")
            except SyntaxError:
                pass
    else:
        print >>sys.stderr, __doc__